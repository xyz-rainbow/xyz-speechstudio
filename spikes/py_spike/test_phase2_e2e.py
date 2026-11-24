import json
import subprocess
import time
from pathlib import Path

import httpx

RUST_NVML = r"N:\spikes\rust_spike\target\release\rust_spike.exe"


def vram() -> dict:
    return json.loads(subprocess.check_output([RUST_NVML, "nvml"], text=True).strip())


def main() -> None:
    base_vram = vram()
    print("BASELINE_VRAM:", base_vram, flush=True)

    err = open(r"N:\data\tmp\orch_phase2_test.stderr.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [r"N:\.venvs\core\Scripts\python.exe", "-u", "-m", "backend.orchestrator.main", "--port", "0"],
        cwd=r"N:\\",
        stdout=subprocess.PIPE,
        stderr=err,
        text=True,
        bufsize=1,
    )
    real_pid = None
    saved_copy = Path(r"N:\data\tmp\test_save_as_copy.wav")
    try:
        hs = json.loads(proc.stdout.readline().strip())
        port, real_pid = hs["port"], hs["pid"]
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(timeout=180.0) as c:
            profs = c.get(f"{base}/api/profiles").json()["profiles"]
            mario = next(p for p in profs if p["id"] == "mario")
            assert mario["ready"] is True
            print("MARIO_PROFILE_OK:", mario["name"], mario["language"], flush=True)

            # 1. Play mode (temp buffer, must NOT add to history)
            r_play = c.post(
                f"{base}/api/tts/synthesize",
                json={"profile_id": "mario", "text": "Prueba temporal en Studio.", "mode": "play"},
            )
            r_play.raise_for_status()
            d_play = r_play.json()
            wav_play = c.get(f"{base}{d_play['audio_url']}")
            assert wav_play.status_code == 200 and wav_play.content[:4] == b"RIFF" and len(wav_play.content) > 20000
            assert len(c.get(f"{base}/api/tts/history").json()["history"]) == 0
            peak_vram = vram()
            print(
                "PLAY_MODE_OK:",
                d_play["duration_s"],
                "s, bytes=",
                len(wav_play.content),
                "peak_vram=",
                peak_vram["used_mib"],
                "MiB",
                flush=True,
            )

            # 2. Export WAV mode + Save As + Delete
            r_wav = c.post(
                f"{base}/api/tts/synthesize",
                json={"profile_id": "mario", "text": "Prueba exportada para historial.", "mode": "wav"},
            )
            r_wav.raise_for_status()
            rec = r_wav.json()["record"]
            hist = c.get(f"{base}/api/tts/history").json()["history"]
            assert len(hist) == 1 and hist[0]["id"] == rec["id"]

            r_sa = c.post(
                f"{base}/api/tts/history/{rec['id']}/save_as",
                json={"dest_path": str(saved_copy)},
            )
            r_sa.raise_for_status()
            assert saved_copy.exists() and saved_copy.read_bytes()[:4] == b"RIFF"
            assert r_sa.json()["record"]["saved_path"] == str(saved_copy)

            r_del = c.delete(f"{base}/api/tts/history/{rec['id']}")
            r_del.raise_for_status()
            assert len(c.get(f"{base}/api/tts/history").json()["history"]) == 0
            print("WAV_HISTORY_SAVEAS_DELETE_OK:", rec["id"], flush=True)

            # 3. OpenAI-compatible POST /v1/audio/speech
            r_api = c.post(
                f"{base}/v1/audio/speech",
                json={"model": "qwen3-1.7b", "input": "Prueba de endpoint local.", "voice": "mario"},
            )
            assert r_api.status_code == 200, r_api.text
            assert "audio/wav" in r_api.headers.get("content-type", "")
            assert r_api.content[:4] == b"RIFF" and len(r_api.content) > 20000
            print("OPENAI_SPEECH_API_OK: bytes=", len(r_api.content), flush=True)

            # 4. Eject Qwen worker and verify VRAM freed
            r_ej = c.post(f"{base}/api/workers/qwen/eject")
            r_ej.raise_for_status()
            assert r_ej.json()["workers"]["qwen"]["running"] is False
            time.sleep(1.2)
            post_vram = vram()
            delta = abs(post_vram["used_mib"] - base_vram["used_mib"])
            print("POST_EJECT_VRAM:", post_vram, f"delta={delta} MiB", flush=True)
            assert delta <= 150, f"VRAM leaked: delta={delta}"
    finally:
        saved_copy.unlink(missing_ok=True)
        if real_pid and real_pid != proc.pid:
            subprocess.run(["taskkill", "/F", "/PID", str(real_pid)], capture_output=True)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        err.close()

    print("PHASE2_E2E_ALL_OK", flush=True)


if __name__ == "__main__":
    main()
