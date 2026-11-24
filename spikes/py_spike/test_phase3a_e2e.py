import json
import subprocess
import time
from pathlib import Path

import httpx

RUST_NVML = r"N:\spikes\rust_spike\target\release\rust_spike.exe"
TEST_WAV = Path(r"Z:\[🤖] [Models]\tts\qwen3-1.7b\mario-new-tts\test-1-saludo.wav")


def vram() -> dict:
    return json.loads(subprocess.check_output([RUST_NVML, "nvml"], text=True).strip())


def main() -> None:
    base_vram = vram()
    print("BASELINE_VRAM:", base_vram, flush=True)

    err = open(r"N:\data\tmp\orch_phase3a_test.stderr.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [r"N:\.venvs\core\Scripts\python.exe", "-u", "-m", "backend.orchestrator.main", "--port", "0"],
        cwd=r"N:\\",
        stdout=subprocess.PIPE,
        stderr=err,
        text=True,
        bufsize=1,
    )
    real_pid = None
    orig_settings = None
    try:
        hs = json.loads(proc.stdout.readline().strip())
        port, real_pid = hs["port"], hs["pid"]
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(timeout=180.0) as c:
            sresp = c.get(f"{base}/api/settings").json()
            orig_settings = dict(sresp["settings"])

            # 1. Load STT worker (faster-whisper-base)
            r_load = c.post(f"{base}/api/workers/stt/load", json={"model_id": "faster-whisper-base"})
            r_load.raise_for_status()
            w = r_load.json()["workers"]["stt"]
            assert w["running"] is True and w["model_id"] == "faster-whisper-base"
            peak_vram = vram()
            print("STT_LOAD_OK:", w["pid"], "peak_vram=", peak_vram["used_mib"], "MiB", flush=True)

            # 2. Local file transcription
            r_tr = c.post(f"{base}/api/stt/transcribe", json={"audio_path": str(TEST_WAV), "language": "es"})
            r_tr.raise_for_status()
            d_tr = r_tr.json()
            assert "mario" in d_tr["text"].lower(), d_tr
            print("LOCAL_TRANSCRIBE_OK:", d_tr["text"], flush=True)

            # 3. Verify Serve defaults OFF (403), then enable Serve ON for multipart /v1/audio/transcriptions
            assert orig_settings["api_endpoint_enabled"] is False, orig_settings
            assert orig_settings["external_endpoints"] == [], orig_settings
            with open(TEST_WAV, "rb") as fh:
                r_default_off = c.post(
                    f"{base}/v1/audio/transcriptions",
                    files={"file": ("test-1-saludo.wav", fh, "audio/wav")},
                )
            assert r_default_off.status_code == 403, r_default_off.text

            c.put(f"{base}/api/settings", json={**orig_settings, "api_endpoint_enabled": True}).raise_for_status()
            with open(TEST_WAV, "rb") as fh:
                r_mp = c.post(
                    f"{base}/v1/audio/transcriptions",
                    data={"model": "faster-whisper-base", "language": "es"},
                    files={"file": ("test-1-saludo.wav", fh, "audio/wav")},
                )
            assert r_mp.status_code == 200, r_mp.text
            assert "mario" in r_mp.json()["text"].lower()
            print("MULTIPART_API_OK (with Serve default OFF->ON):", r_mp.json()["text"], flush=True)

            # 4. Bearer token enforcement + Serve ON/OFF
            protected = {**orig_settings, "api_endpoint_enabled": True, "api_bearer_token": "sk-test-secret"}
            c.put(f"{base}/api/settings", json=protected).raise_for_status()

            with open(TEST_WAV, "rb") as fh:
                r_401 = c.post(
                    f"{base}/v1/audio/transcriptions",
                    files={"file": ("test-1-saludo.wav", fh, "audio/wav")},
                )
            assert r_401.status_code == 401, r_401.text

            with open(TEST_WAV, "rb") as fh:
                r_200 = c.post(
                    f"{base}/v1/audio/transcriptions",
                    headers={"Authorization": "Bearer sk-test-secret"},
                    files={"file": ("test-1-saludo.wav", fh, "audio/wav")},
                )
            assert r_200.status_code == 200, r_200.text

            disabled = {**orig_settings, "api_endpoint_enabled": False, "api_bearer_token": ""}
            c.put(f"{base}/api/settings", json=disabled).raise_for_status()
            with open(TEST_WAV, "rb") as fh:
                r_403 = c.post(
                    f"{base}/v1/audio/transcriptions",
                    files={"file": ("test-1-saludo.wav", fh, "audio/wav")},
                )
            assert r_403.status_code == 403, r_403.text
            print("SERVE_ON_OFF_AND_BEARER_OK: 401/200/403", flush=True)

            # Restore clean settings
            c.put(f"{base}/api/settings", json=orig_settings).raise_for_status()

            # 5. Group eject STT and verify VRAM freed
            r_ej = c.post(f"{base}/api/workers/eject_group/stt")
            r_ej.raise_for_status()
            assert r_ej.json()["workers"]["stt"]["running"] is False
            time.sleep(1.2)
            post_vram = vram()
            delta = abs(post_vram["used_mib"] - base_vram["used_mib"])
            print("POST_EJECT_STT_VRAM:", post_vram, f"delta={delta} MiB", flush=True)
            assert delta <= 150, f"VRAM leaked: delta={delta}"

            # 6. Catalog + Hugging Face URL inspector
            r_cat = c.get(f"{base}/api/models/catalog")
            r_cat.raise_for_status()
            models = r_cat.json()["models"]
            tts_inst = [m for m in models if m["kind"] == "tts" and m["installed"]]
            stt_uninst = [m for m in models if m["kind"] == "stt" and not m["installed"]]
            assert any(m["id"] == "qwen3-1.7b-base" for m in tts_inst), models
            assert len(stt_uninst) >= 1, models
            print(
                f"CATALOG_OK: total={len(models)} tts_installed={len(tts_inst)} stt_uninstalled={len(stt_uninst)}",
                flush=True,
            )

            r_hf = c.post(
                f"{base}/api/models/hf/inspect",
                json={"url": "https://huggingface.co/Serveurperso/Qwen3-TTS-GGUF"},
            )
            r_hf.raise_for_status()
            hf_files = r_hf.json()["files"]
            assert any(f["filename"].endswith(".gguf") for f in hf_files), hf_files
            print(f"HF_INSPECT_OK: repo={r_hf.json()['repo_id']} files={len(hf_files)}", flush=True)
    finally:
        if orig_settings:
            try:
                httpx.put(f"http://127.0.0.1:{port}/api/settings", json=orig_settings, timeout=5.0)
            except Exception:
                pass
        if real_pid and real_pid != proc.pid:
            subprocess.run(["taskkill", "/F", "/PID", str(real_pid)], capture_output=True)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        err.close()

    print("PHASE3A_E2E_ALL_OK", flush=True)


if __name__ == "__main__":
    main()
