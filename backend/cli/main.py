from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Optional

import httpx

from backend.orchestrator.config import APP_ROOT, RUNTIME_JSON_PATH


def _play_wav_file(wav_path: Path) -> None:
    """Play a WAV file over system speakers on Windows, macOS, or Linux."""
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
        return
    if sys.platform == "darwin":
        if shutil.which("afplay"):
            subprocess.run(["afplay", str(wav_path)], check=True)
            return
        raise RuntimeError("afplay not found on macOS to play audio.")

    for player in ("paplay", "pw-play", "aplay", "ffplay"):
        exe = shutil.which(player)
        if not exe:
            continue
        cmd = (
            [exe, "-nodisp", "-autoexit", "-loglevel", "quiet", str(wav_path)]
            if player == "ffplay"
            else [exe, str(wav_path)]
        )
        subprocess.run(cmd, check=True)
        return

    raise RuntimeError(
        "No supported audio player found on Linux (install paplay, pw-play, aplay, or ffplay)."
    )


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _is_alive(base_url: str) -> bool:
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{base_url}/health")
            return resp.status_code == 200
    except Exception:
        return False


class OrchestratorClient:
    """Connect to a running Speech Studio backend or spawn a temporary one."""

    def __init__(self, explicit_url: Optional[str] = None) -> None:
        self.explicit_url = explicit_url.rstrip("/") if explicit_url else None
        self.base_url: str = ""
        self._proc: Optional[subprocess.Popen[str]] = None
        self._spawned_pid: Optional[int] = None
        self._http: Optional[httpx.Client] = None

    def __enter__(self) -> "OrchestratorClient":
        if self.explicit_url:
            if not _is_alive(self.explicit_url):
                raise RuntimeError(f"Speech Studio API is not reachable at {self.explicit_url}")
            self.base_url = self.explicit_url
            self._http = httpx.Client(base_url=self.base_url, timeout=300.0)
            return self

        if RUNTIME_JSON_PATH.is_file():
            try:
                info = json.loads(RUNTIME_JSON_PATH.read_text(encoding="utf-8"))
                port = info.get("port")
                host = info.get("host") or "127.0.0.1"
                if port:
                    candidate = f"http://{host}:{port}"
                    if _is_alive(candidate):
                        self.base_url = candidate
                        self._http = httpx.Client(base_url=self.base_url, timeout=300.0)
                        return self
            except Exception:
                pass

        # Spawn temporary headless orchestrator on an ephemeral port
        cmd = [sys.executable, "-u", "-m", "backend.orchestrator.main", "--port", "0"]
        popen_kwargs: dict[str, Any] = {
            "cwd": str(APP_ROOT),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            popen_kwargs["start_new_session"] = True
        self._proc = subprocess.Popen(cmd, **popen_kwargs)

        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                err_out = ""
                try:
                    if self._proc.stderr:
                        err_out = self._proc.stderr.read().strip()
                except Exception:
                    pass
                raise RuntimeError(
                    f"Temporary Speech Studio backend exited early ({self._proc.returncode}): {err_out}"
                )
            if self._proc.stdout:
                line = self._proc.stdout.readline().strip()
                if line.startswith("{"):
                    try:
                        payload = json.loads(line)
                        if "port" in payload:
                            self._spawned_pid = int(payload.get("pid") or self._proc.pid)
                            self.base_url = f"http://127.0.0.1:{payload['port']}"
                            self._http = httpx.Client(base_url=self.base_url, timeout=300.0)
                            return self
                    except json.JSONDecodeError:
                        pass
            time.sleep(0.05)

        self.__exit__(None, None, None)
        raise RuntimeError("Timed out starting temporary Speech Studio backend.")

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._http is not None:
            try:
                self._http.close()
            except Exception:
                pass
            self._http = None

        if self._proc is not None:
            pid = self._spawned_pid or self._proc.pid
            if sys.platform == "win32" and pid:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except Exception:
                    pass
            elif pid:
                try:
                    os.killpg(pid, signal.SIGTERM)
                    deadline = time.monotonic() + 2.0
                    while self._proc.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.05)
                    if self._proc.poll() is None:
                        os.killpg(pid, signal.SIGKILL)
                except Exception:
                    pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

            if RUNTIME_JSON_PATH.is_file() and pid:
                try:
                    cur = json.loads(RUNTIME_JSON_PATH.read_text(encoding="utf-8"))
                    if cur.get("pid") == pid:
                        RUNTIME_JSON_PATH.unlink(missing_ok=True)
                except Exception:
                    pass

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        assert self._http is not None
        resp = self._http.request(method, path, **kwargs)
        if resp.status_code >= 400:
            detail = resp.text
            try:
                data = resp.json()
                if isinstance(data, dict) and data.get("detail"):
                    detail = str(data["detail"])
            except Exception:
                pass
            raise RuntimeError(f"HTTP {resp.status_code} on {method} {path}: {detail}")
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.content


def _normalize_shorthands(argv: list[str]) -> list[str]:
    """Allow top-level shorthands like `--models`, `--status`, `--profiles`, `--config`, `--endpoints`."""
    shorthand_map = {
        "--models": "models",
        "--status": "status",
        "--inspect": "inspect",
        "--profiles": "profiles",
        "--config": "config",
        "--endpoints": "endpoints",
    }
    if not argv:
        return argv
    out = list(argv)
    for idx, token in enumerate(out):
        if token in shorthand_map and not any(
            not t.startswith("-") for t in out[:idx]
        ):
            out[idx] = shorthand_map[token]
            break
    return out


def _coerce_value(raw: str) -> Any:
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low == "null" or low == "none":
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        if "." in raw:
            return float(raw)
    except ValueError:
        pass
    return raw


def _cmd_status(client: OrchestratorClient, args: argparse.Namespace) -> int:
    data = client.request("GET", "/api/inspect")
    if args.json:
        _print_json(data)
        return 0

    h = data["health"]
    s = data["settings"]
    vram = data["vram"]
    workers = data.get("workers", {}).get("workers", {})
    models_inst = data.get("models_installed", [])
    profiles_list = data.get("profiles", [])
    endpoints = data.get("endpoints", [])

    print(f"Speech Studio API: {client.base_url} (PID {h['pid']})")
    print(f"Models Dir:        {data['resolved_models_dir']}")
    print(f"Outputs Dir:       {data['resolved_outputs_dir']}")
    if vram["total_mib"] > 0:
        print(f"GPU VRAM:          {vram['used_mib']} / {vram['total_mib']} MiB used ({vram['free_mib']} MiB free)")
    print(f"TTS Source:        {s['tts_source']} (active model: {s['active_tts_model'] or 'none'}, device: {s['tts_device']})")
    print(f"STT Source:        {s['stt_source']} (active model: {s['active_stt_model'] or 'none'}, device: {s['stt_device']})")
    print(f"Installed Models:  {len(models_inst)}")
    print(f"Voice Profiles:    {len(profiles_list)}")
    print(f"External Endpoints:{len(endpoints)}")
    running = [
        f"{fam}={info.get('model_id')} ({info.get('device')})"
        for fam, info in workers.items()
        if info.get("running")
    ]
    print(f"Loaded Workers:    {', '.join(running) if running else 'none'}")
    return 0


def _cmd_play(client: OrchestratorClient, args: argparse.Namespace) -> int:
    text = " ".join(args.text).strip()
    if not text:
        raise RuntimeError("Text to synthesize cannot be empty.")

    settings = client.request("GET", "/api/settings")["settings"]
    profile_id = args.profile
    if not profile_id:
        profs = client.request("GET", "/api/profiles").get("profiles", [])
        ready_profs = [p for p in profs if p.get("ready")]
        if ready_profs:
            profile_id = ready_profs[0]["id"]
        elif profs:
            profile_id = profs[0]["id"]
        elif settings.get("tts_source") == "endpoint":
            profile_id = "default"
        else:
            raise RuntimeError(
                "No voice profile found. Create a voice profile first or configure/switch TTS to an external endpoint."
            )

    mode = "wav" if args.save else "play"
    payload = {
        "profile_id": profile_id,
        "text": text,
        "language": args.lang,
        "mode": mode,
        "seed": args.seed,
        "force_stop_captions": args.force_stop_captions,
    }
    res = client.request("POST", "/api/tts/synthesize", json=payload)

    audio_bytes = client.request("GET", res["audio_url"])
    out_path: Optional[Path] = None
    tmp_file: Optional[Path] = None

    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio_bytes)
    elif res.get("file_path"):
        out_path = Path(res["file_path"])
    elif not args.no_play:
        fd, tmp_name = tempfile.mkstemp(prefix="speechstudio_play_", suffix=".wav")
        os.close(fd)
        tmp_file = Path(tmp_name)
        tmp_file.write_bytes(audio_bytes)
        out_path = tmp_file

    played = False
    try:
        if not args.no_play and out_path is not None:
            _play_wav_file(out_path)
            played = True
    finally:
        if tmp_file is not None:
            tmp_file.unlink(missing_ok=True)

    output = {
        "ok": True,
        "mode": mode,
        "played": played,
        "saved_path": str(out_path) if (args.out or args.save) and out_path else None,
        "duration_s": res.get("duration_s"),
        "sr": res.get("sr"),
        "elapsed_s": res.get("elapsed_s"),
        "rtf": res.get("rtf"),
    }
    if args.json:
        _print_json(output)
    else:
        saved_msg = f" -> saved: {output['saved_path']}" if output["saved_path"] else ""
        print(
            f"Generated {output['duration_s']}s audio in {output['elapsed_s']}s "
            f"(played={played}){saved_msg}"
        )
    return 0


def _wait_download_job(client: OrchestratorClient, job_id: str) -> dict[str, Any]:
    while True:
        cat = client.request("GET", "/api/models/catalog")
        job = next((j for j in cat.get("downloads", []) if j["job_id"] == job_id), None)
        if job is None:
            raise RuntimeError(f"Download job vanished: {job_id}")
        status = job.get("status")
        if status == "completed":
            return job
        if status in ("failed", "cancelled"):
            raise RuntimeError(f"Download {status}: {job.get('error') or job_id}")
        time.sleep(1.0)


def _cmd_models(client: OrchestratorClient, args: argparse.Namespace) -> int:
    sub = args.models_action or "list"

    if sub == "list":
        cat = client.request("GET", "/api/models/catalog")
        items = cat.get("models", [])
        if args.installed:
            items = [m for m in items if m.get("installed")]
        if args.kind:
            items = [m for m in items if m.get("kind") == args.kind]
        if args.json:
            _print_json({"models_dir": cat.get("models_dir"), "models": items})
            return 0
        print(f"Models Dir: {cat.get('models_dir')}")
        if not items:
            print("No matching models.")
            return 0
        for m in items:
            status = "INSTALLED" if m.get("installed") else "AVAILABLE"
            fam = m.get("family_name") or m.get("engine")
            print(
                f"- [{m['kind'].upper()}] {m['id']} ({m['name']}) | {fam} | "
                f"{status} | {m.get('disk_mb', 0)} MB | {m.get('vram_mib', 0)} MiB"
            )
        return 0

    if sub == "search":
        params = urllib.parse.urlencode(
            {
                "kind": args.kind or "tts",
                "q": args.query,
                "page": args.page,
                "page_size": args.page_size,
            }
        )
        res = client.request("GET", f"/api/models/hub/search?{params}")
        if args.json:
            _print_json(res)
            return 0
        print(f"Hub Search ({res['kind'].upper()}, page {res['page']}, has_more={res['has_more']}):")
        for item in res.get("items", []):
            print(f"- {item['repo_id']} | {item['downloads']} dl | tags={','.join(item.get('tags', [])[:4])}")
        return 0

    if sub == "inspect":
        res = client.request("POST", "/api/models/url/inspect", json={"url": args.url})
        if args.json:
            _print_json(res)
            return 0
        print(f"Source: {res['source']} | Repo: {res['repo_id']} | Suggested: {res['suggested_name']}")
        for f in res.get("files", []):
            rec = " [recommended]" if f.get("recommended") else ""
            print(f"  - {f['filename']} ({f['size_mb']} MB){rec}")
        return 0

    if sub == "download":
        payload = {"model_id": args.model_id, "quant_id": args.quant}
        res = client.request("POST", "/api/models/download", json=payload)
        job = res["job"]
        if args.wait:
            job = _wait_download_job(client, job["job_id"])
        if args.json:
            _print_json({"job": job})
            return 0
        print(f"Download {job['job_id']} ({job['model_id']}): status={job['status']} progress={job['progress']}%")
        return 0

    if sub == "install-url":
        info = client.request("POST", "/api/models/url/inspect", json={"url": args.url})
        all_files = info.get("files", [])
        if args.files:
            wanted = [x.strip() for x in args.files.split(",") if x.strip()]
        else:
            wanted = [
                f["filename"]
                for f in all_files
                if f.get("recommended") or f["filename"].endswith((".json", ".txt"))
            ] or [f["filename"] for f in all_files[:4]]
        direct_urls = {
            f["filename"]: f["download_url"]
            for f in all_files
            if f["filename"] in wanted and f.get("download_url")
        }
        payload = {
            "source": info.get("source", "huggingface"),
            "repo_id": info["repo_id"],
            "name": args.name or info["suggested_name"],
            "kind": args.kind,
            "files": wanted,
            "direct_urls": direct_urls,
        }
        res = client.request("POST", "/api/models/url/install", json=payload)
        job = res["job"]
        if args.wait:
            job = _wait_download_job(client, job["job_id"])
        if args.json:
            _print_json({"job": job})
            return 0
        print(f"Install job {job['job_id']}: status={job['status']} files={len(wanted)}")
        return 0

    if sub == "import":
        res = client.request(
            "POST",
            "/api/models/local/import",
            json={
                "source_path": str(Path(args.path).expanduser().resolve()),
                "name": args.name or Path(args.path).stem,
                "kind": args.kind,
            },
        )
        if args.json:
            _print_json(res)
            return 0
        m = res["model"]
        print(f"Imported [{m['kind'].upper()}] {m['id']} ({m['name']})")
        return 0

    if sub == "load":
        cat = client.request("GET", "/api/models/catalog")
        entry = next((m for m in cat.get("models", []) if m["id"] == args.model_id), None)
        if entry is None:
            raise RuntimeError(f"Unknown model ID: {args.model_id}")
        if entry["kind"] == "stt":
            route = "/api/workers/stt/load"
        elif entry.get("engine") == "xtts":
            route = "/api/workers/xtts/load"
        elif entry.get("engine") == "qwen":
            route = "/api/workers/qwen/load"
        else:
            raise RuntimeError(f"Engine '{entry.get('engine')}' cannot be loaded in this runtime yet.")
        payload: dict[str, Any] = {"model_id": args.model_id, "force_stop_captions": True}
        if args.device:
            payload["device"] = args.device
        snap = client.request("POST", route, json=payload)
        if args.json:
            _print_json(snap)
            return 0
        print(f"Loaded {args.model_id} via {route}")
        return 0

    if sub == "eject":
        target = args.target
        if target in ("tts", "stt"):
            res = client.request("POST", f"/api/workers/eject_group/{target}")
        elif target in ("qwen", "xtts"):
            res = client.request("POST", f"/api/workers/{target}/eject")
        elif target == "all":
            res = {
                "tts": client.request("POST", "/api/workers/eject_group/tts"),
                "stt": client.request("POST", "/api/workers/eject_group/stt"),
            }
        else:
            raise RuntimeError(f"Invalid eject target: {target}")
        if args.json:
            _print_json(res)
            return 0
        print(f"Ejected worker target: {target}")
        return 0

    if sub == "remove":
        res = client.request("DELETE", f"/api/models/{args.model_id}")
        if args.json:
            _print_json(res)
            return 0
        print(f"Removed local model: {args.model_id}")
        return 0

    raise RuntimeError(f"Unsupported models action: {sub}")


def _cmd_profiles(client: OrchestratorClient, args: argparse.Namespace) -> int:
    sub = args.profiles_action or "list"
    if sub == "list":
        res = client.request("GET", "/api/profiles")
        if args.json:
            _print_json(res)
            return 0
        items = res.get("profiles", [])
        if not items:
            print("No voice profiles configured.")
            return 0
        for p in items:
            print(
                f"- {p['id']} ({p['name']}) | engine={p['engine']} | "
                f"lang={p['language']} | ready={p['ready']}"
            )
        return 0

    if sub == "create":
        payload = {
            "name": args.name,
            "language": args.lang,
            "engine": args.engine,
            "ref_audio_path": str(Path(args.ref_audio).expanduser().resolve()) if args.ref_audio else "",
            "ref_text": args.ref_text,
            "build_voice": not args.no_build,
            "force_stop_captions": True,
        }
        res = client.request("POST", "/api/profiles", json=payload)
        if args.json:
            _print_json(res)
            return 0
        p = res["profile"]
        print(f"Created profile {p['id']} ({p['name']}) | ready={p['ready']}")
        return 0

    if sub == "delete":
        res = client.request("DELETE", f"/api/profiles/{args.profile_id}")
        if args.json:
            _print_json(res)
            return 0
        print(f"Deleted profile: {args.profile_id}")
        return 0

    raise RuntimeError(f"Unsupported profiles action: {sub}")


def _cmd_transcribe(client: OrchestratorClient, args: argparse.Namespace) -> int:
    audio_path = str(Path(args.audio_path).expanduser().resolve())
    payload: dict[str, Any] = {"audio_path": audio_path}
    if args.lang:
        payload["language"] = args.lang
    if args.model:
        payload["model_id"] = args.model
    res = client.request("POST", "/api/stt/transcribe", json=payload)
    if args.json:
        _print_json(res)
        return 0
    print(res.get("text", "").strip())
    return 0


def _cmd_config(client: OrchestratorClient, args: argparse.Namespace) -> int:
    sub = args.config_action or "show"
    if sub == "show":
        res = client.request("GET", "/api/settings")
        if args.json:
            _print_json(res)
            return 0
        for k, v in res["settings"].items():
            if k == "external_endpoints":
                print(f"external_endpoints: [{len(v)} entries]")
            else:
                print(f"{k}: {v}")
        return 0

    if sub == "set":
        current = client.request("GET", "/api/settings")["settings"]
        for pair in args.pairs:
            if "=" not in pair:
                raise RuntimeError(f"Expected KEY=VALUE, got: {pair}")
            k, raw_v = pair.split("=", 1)
            key = k.strip()
            if key not in current:
                raise RuntimeError(f"Unknown setting key: {key}")
            current[key] = _coerce_value(raw_v)
        saved = client.request("PUT", "/api/settings", json=current)
        if args.json:
            _print_json(saved)
            return 0
        print("Settings updated.")
        return 0

    raise RuntimeError(f"Unsupported config action: {sub}")


def _cmd_endpoints(client: OrchestratorClient, args: argparse.Namespace) -> int:
    sub = args.endpoints_action or "list"
    if sub == "list":
        settings = client.request("GET", "/api/settings")["settings"]
        eps = settings.get("external_endpoints", [])
        if args.json:
            _print_json(
                {
                    "active_tts_endpoint_id": settings.get("active_tts_endpoint_id"),
                    "active_stt_endpoint_id": settings.get("active_stt_endpoint_id"),
                    "endpoints": eps,
                }
            )
            return 0
        if not eps:
            print("No external endpoints configured.")
            return 0
        for ep in eps:
            print(
                f"- [{ep['kind'].upper()}] {ep['id']} | {ep['name']} | "
                f"{ep['protocol']} | {ep['base_url']} | model={ep.get('model', '')}"
            )
        return 0

    if sub == "test":
        res = client.request("POST", f"/api/endpoints/{args.endpoint_id}/test")
        if args.json:
            _print_json(res)
            return 0
        print(f"Endpoint {args.endpoint_id}: ok={res.get('ok')} detail={res.get('detail')}")
        return 0

    if sub == "select":
        settings = client.request("GET", "/api/settings")["settings"]
        key = "active_tts_endpoint_id" if args.kind == "tts" else "active_stt_endpoint_id"
        settings[key] = args.endpoint_id
        if args.use:
            src_key = "tts_source" if args.kind == "tts" else "stt_source"
            settings[src_key] = "endpoint"
        saved = client.request("PUT", "/api/settings", json=settings)
        if args.json:
            _print_json(saved)
            return 0
        print(f"Selected {args.kind.upper()} endpoint: {args.endpoint_id}")
        return 0

    if sub == "delete":
        settings = client.request("GET", "/api/settings")["settings"]
        settings["external_endpoints"] = [
            ep for ep in settings.get("external_endpoints", []) if ep.get("id") != args.endpoint_id
        ]
        if settings.get("active_tts_endpoint_id") == args.endpoint_id:
            settings["active_tts_endpoint_id"] = ""
        if settings.get("active_stt_endpoint_id") == args.endpoint_id:
            settings["active_stt_endpoint_id"] = ""
        saved = client.request("PUT", "/api/settings", json=settings)
        if args.json:
            _print_json(saved)
            return 0
        print(f"Deleted endpoint: {args.endpoint_id}")
        return 0

    raise RuntimeError(f"Unsupported endpoints action: {sub}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="speechstudio",
        description="Speech Studio CLI (connects to running GUI or spawns a temporary orchestrator).",
    )
    parser.add_argument("--url", help="Explicit Speech Studio API base URL (e.g. http://127.0.0.1:41933)")
    sub = parser.add_subparsers(dest="command", required=True)

    # play
    p_play = sub.add_parser("play", help="Synthesize speech and play over speakers or save WAV.")
    p_play.add_argument("text", nargs="+", help="Text to synthesize.")
    p_play.add_argument("--profile", "-p", help="Voice profile ID (defaults to first ready profile).")
    p_play.add_argument("--lang", "-l", help="Language override (e.g. Spanish, English).")
    p_play.add_argument("--out", "-o", help="Write generated WAV to this path.")
    p_play.add_argument("--save", action="store_true", help="Also save to Outputs folder and history.")
    p_play.add_argument("--no-play", action="store_true", help="Skip speaker playback.")
    p_play.add_argument("--seed", type=int, default=-1, help="Synthesis seed.")
    p_play.add_argument("--force-stop-captions", action="store_true")
    p_play.add_argument("--json", action="store_true")

    # status / inspect
    for cmd_name in ("status", "inspect"):
        p_st = sub.add_parser(cmd_name, help="Inspect live app settings, VRAM, models, profiles and workers.")
        p_st.add_argument("--json", action="store_true")

    # models
    p_mod = sub.add_parser("models", help="List, search, download, import, load, eject or remove models.")
    mod_sub = p_mod.add_subparsers(dest="models_action")

    p_ml = mod_sub.add_parser("list", help="List catalog models.")
    p_ml.add_argument("--installed", action="store_true")
    p_ml.add_argument("--kind", choices=["tts", "stt"])
    p_ml.add_argument("--json", action="store_true")

    p_ms = mod_sub.add_parser("search", help="Search Hugging Face Hub models.")
    p_ms.add_argument("query", nargs="?", default="")
    p_ms.add_argument("--kind", choices=["tts", "stt"], default="tts")
    p_ms.add_argument("--page", type=int, default=1)
    p_ms.add_argument("--page-size", type=int, default=6)
    p_ms.add_argument("--json", action="store_true")

    p_mi = mod_sub.add_parser("inspect", help="Inspect a Hugging Face, ModelScope or direct file URL.")
    p_mi.add_argument("url")
    p_mi.add_argument("--json", action="store_true")

    p_md = mod_sub.add_parser("download", help="Download a built-in catalog model.")
    p_md.add_argument("model_id")
    p_md.add_argument("--quant")
    p_md.add_argument("--wait", action="store_true")
    p_md.add_argument("--json", action="store_true")

    p_mu = mod_sub.add_parser("install-url", help="Install a model from Hugging Face, ModelScope or direct URL.")
    p_mu.add_argument("url")
    p_mu.add_argument("--name")
    p_mu.add_argument("--kind", choices=["tts", "stt"], default="stt")
    p_mu.add_argument("--files", help="Comma-separated filenames to download.")
    p_mu.add_argument("--wait", action="store_true")
    p_mu.add_argument("--json", action="store_true")

    p_imp = mod_sub.add_parser("import", help="Import a local model folder or file.")
    p_imp.add_argument("path")
    p_imp.add_argument("--kind", choices=["tts", "stt"], required=True)
    p_imp.add_argument("--name")
    p_imp.add_argument("--json", action="store_true")

    p_mld = mod_sub.add_parser("load", help="Load a local model onto GPU or CPU.")
    p_mld.add_argument("model_id")
    p_mld.add_argument("--device", choices=["gpu", "cpu"])
    p_mld.add_argument("--json", action="store_true")

    p_mej = mod_sub.add_parser("eject", help="Unload worker(s): tts, stt, qwen, xtts, all.")
    p_mej.add_argument("target", choices=["tts", "stt", "qwen", "xtts", "all"])
    p_mej.add_argument("--json", action="store_true")

    p_mrm = mod_sub.add_parser("remove", help="Delete local files for an installed model.")
    p_mrm.add_argument("model_id")
    p_mrm.add_argument("--json", action="store_true")

    p_mod.add_argument("--installed", action="store_true")
    p_mod.add_argument("--kind", choices=["tts", "stt"])
    p_mod.add_argument("--json", action="store_true")

    # profiles
    p_prof = sub.add_parser("profiles", help="List, create or delete voice profiles.")
    prof_sub = p_prof.add_subparsers(dest="profiles_action")
    p_pl = prof_sub.add_parser("list")
    p_pl.add_argument("--json", action="store_true")

    p_pc = prof_sub.add_parser("create")
    p_pc.add_argument("--name", required=True)
    p_pc.add_argument("--engine", choices=["qwen", "xtts"], default="qwen")
    p_pc.add_argument("--lang", default="Spanish")
    p_pc.add_argument("--ref-audio", default="")
    p_pc.add_argument("--ref-text", default="")
    p_pc.add_argument("--no-build", action="store_true")
    p_pc.add_argument("--json", action="store_true")

    p_pd = prof_sub.add_parser("delete")
    p_pd.add_argument("profile_id")
    p_pd.add_argument("--json", action="store_true")
    p_prof.add_argument("--json", action="store_true")

    # transcribe
    p_tr = sub.add_parser("transcribe", help="Transcribe an audio file using the active STT source.")
    p_tr.add_argument("audio_path")
    p_tr.add_argument("--lang")
    p_tr.add_argument("--model")
    p_tr.add_argument("--json", action="store_true")

    # config
    p_cfg = sub.add_parser("config", help="Show or update app settings.")
    cfg_sub = p_cfg.add_subparsers(dest="config_action")
    p_cs = cfg_sub.add_parser("show")
    p_cs.add_argument("--json", action="store_true")
    p_cset = cfg_sub.add_parser("set")
    p_cset.add_argument("pairs", nargs="+", help="KEY=VALUE pairs.")
    p_cset.add_argument("--json", action="store_true")
    p_cfg.add_argument("--json", action="store_true")

    # endpoints
    p_ep = sub.add_parser("endpoints", help="List, test, select or delete external API endpoints.")
    ep_sub = p_ep.add_subparsers(dest="endpoints_action")
    p_el = ep_sub.add_parser("list")
    p_el.add_argument("--json", action="store_true")
    p_et = ep_sub.add_parser("test")
    p_et.add_argument("endpoint_id")
    p_et.add_argument("--json", action="store_true")
    p_es = ep_sub.add_parser("select")
    p_es.add_argument("endpoint_id")
    p_es.add_argument("--kind", choices=["tts", "stt"], required=True)
    p_es.add_argument("--use", action="store_true", help="Also switch TTS/STT source to endpoint.")
    p_es.add_argument("--json", action="store_true")
    p_ed = ep_sub.add_parser("delete")
    p_ed.add_argument("endpoint_id")
    p_ed.add_argument("--json", action="store_true")
    p_ep.add_argument("--json", action="store_true")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    normalized = _normalize_shorthands(raw_argv)
    parser = build_parser()
    args = parser.parse_args(normalized)

    try:
        with OrchestratorClient(explicit_url=args.url) as client:
            if args.command in ("status", "inspect"):
                return _cmd_status(client, args)
            if args.command == "play":
                return _cmd_play(client, args)
            if args.command == "models":
                return _cmd_models(client, args)
            if args.command == "profiles":
                return _cmd_profiles(client, args)
            if args.command == "transcribe":
                return _cmd_transcribe(client, args)
            if args.command == "config":
                return _cmd_config(client, args)
            if args.command == "endpoints":
                return _cmd_endpoints(client, args)
            raise RuntimeError(f"Unknown command: {args.command}")
    except Exception as exc:
        if getattr(args, "json", False):
            _print_json({"ok": False, "error": str(exc)})
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
