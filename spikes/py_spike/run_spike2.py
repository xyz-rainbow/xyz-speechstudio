import json
import subprocess
import time
from pathlib import Path

import httpx

RUST_SPIKE = Path(r"N:\spikes\rust_spike\target\release\rust_spike.exe")
QWEN_PY = Path(r"N:\.venvs\qwen\Scripts\python.exe")
STT_PY = Path(r"N:\.venvs\stt\Scripts\python.exe")
QWEN_WORKER = Path(r"N:\spikes\py_spike\qwen_spike_worker.py")
STT_WORKER = Path(r"N:\spikes\py_spike\stt_spike_worker.py")
LOG_DIR = Path(r"N:\data\tmp")


def get_vram() -> dict:
    out = subprocess.check_output([str(RUST_SPIKE), "nvml"], text=True)
    return json.loads(out.strip())


def spawn_worker(py_exe: Path, script: Path, device: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    err_path = LOG_DIR / f"{script.stem}_{device}.stderr.log"
    err_fh = open(err_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(py_exe), str(script), "--device", device],
        stdout=subprocess.PIPE,
        stderr=err_fh,
        text=True,
        bufsize=1,
    )
    deadline = time.time() + 30.0
    port = None
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                err_fh.close()
                err = err_path.read_text(encoding="utf-8", errors="replace")
                raise RuntimeError(f"Worker {script.name} exited early ({proc.returncode}): {err}")
            time.sleep(0.05)
            continue
        line = line.strip()
        if line.startswith("{"):
            info = json.loads(line)
            port = info["port"]
            break
    if port is None:
        proc.kill()
        err_fh.close()
        raise TimeoutError(f"Timed out waiting for port handshake from {script.name}")
    return proc, port, err_fh


def kill_worker(proc: subprocess.Popen, err_fh):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    err_fh.close()
    time.sleep(1.0)


def post_json(client: httpx.Client, url: str) -> dict:
    resp = client.post(url)
    if resp.status_code >= 400:
        raise RuntimeError(f"POST {url} -> {resp.status_code}: {resp.text}")
    return resp.json()


def get_json(client: httpx.Client, url: str) -> dict:
    resp = client.get(url)
    if resp.status_code >= 400:
        raise RuntimeError(f"GET {url} -> {resp.status_code}: {resp.text}")
    return resp.json()


def main():
    results = []
    baseline = get_vram()
    print(f"[BASELINE] {baseline}", flush=True)

    # Test A: Qwen GPU -> Load -> Synth -> Kill -> VRAM check
    proc, port, err_fh = spawn_worker(QWEN_PY, QWEN_WORKER, "gpu")
    try:
        base_url = f"http://127.0.0.1:{port}"
        with httpx.Client(timeout=120.0) as client:
            h = get_json(client, f"{base_url}/health")
            load_res = post_json(client, f"{base_url}/load")
            peak_a = get_vram()
            synth_res = post_json(client, f"{base_url}/synth")
            print(f"[TEST A] health={h} load={load_res} peak={peak_a} synth={synth_res}", flush=True)
    finally:
        kill_worker(proc, err_fh)
    post_a = get_vram()
    delta_a = abs(post_a["used_mib"] - baseline["used_mib"])
    print(f"[TEST A POST-KILL] {post_a} (delta_vs_baseline={delta_a} MiB)", flush=True)
    assert delta_a <= 150, f"VRAM not released after killing Qwen worker: delta={delta_a} MiB"
    results.append(("Test A: Qwen GPU", baseline["used_mib"], peak_a["used_mib"], post_a["used_mib"], f"synth {synth_res['duration_s']}s in {synth_res['elapsed_s']}s"))

    # Test B: faster-whisper GPU -> Load -> Transcribe -> Kill -> VRAM check
    proc, port, err_fh = spawn_worker(STT_PY, STT_WORKER, "gpu")
    try:
        base_url = f"http://127.0.0.1:{port}"
        with httpx.Client(timeout=180.0) as client:
            load_res = post_json(client, f"{base_url}/load")
            peak_b = get_vram()
            tr_res = post_json(client, f"{base_url}/transcribe")
            print(f"[TEST B] load={load_res} peak={peak_b} transcribe={tr_res}", flush=True)
            txt_low = tr_res["text"].lower()
            assert "mario" in txt_low or "qwen" in txt_low or "clon" in txt_low, f"Unexpected transcript: {tr_res['text']}"
    finally:
        kill_worker(proc, err_fh)
    post_b = get_vram()
    delta_b = abs(post_b["used_mib"] - baseline["used_mib"])
    print(f"[TEST B POST-KILL] {post_b} (delta_vs_baseline={delta_b} MiB)", flush=True)
    assert delta_b <= 150, f"VRAM not released after killing STT worker: delta={delta_b} MiB"
    results.append(("Test B: Whisper GPU", baseline["used_mib"], peak_b["used_mib"], post_b["used_mib"], tr_res["text"]))

    # Test C: faster-whisper CPU mode -> 0 VRAM delta
    pre_c = get_vram()
    proc, port, err_fh = spawn_worker(STT_PY, STT_WORKER, "cpu")
    try:
        base_url = f"http://127.0.0.1:{port}"
        with httpx.Client(timeout=180.0) as client:
            load_res = post_json(client, f"{base_url}/load")
            peak_c = get_vram()
            tr_res_c = post_json(client, f"{base_url}/transcribe")
            print(f"[TEST C] load={load_res} peak={peak_c} transcribe={tr_res_c}", flush=True)
            delta_c = abs(peak_c["used_mib"] - pre_c["used_mib"])
            assert delta_c <= 100, f"CPU mode consumed GPU VRAM: delta={delta_c} MiB"
    finally:
        kill_worker(proc, err_fh)
    post_c = get_vram()
    results.append(("Test C: Whisper CPU", pre_c["used_mib"], peak_c["used_mib"], post_c["used_mib"], tr_res_c["text"]))

    print("\n=== SPIKE 2 SUMMARY ===", flush=True)
    for name, b, p, a, note in results:
        print(f"{name:22s} | base={b:4d} MiB | peak={p:4d} MiB | post={a:4d} MiB | {note}", flush=True)
    print("SPIKE_2_ALL_OK", flush=True)


if __name__ == "__main__":
    main()
