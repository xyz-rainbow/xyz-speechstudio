from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from .config import APP_ROOT, DEFAULT_TMP_DIR


class LiveCaptionsProtectedError(RuntimeError):
    """Raised when evicting STT would interrupt an active Live Captions session."""


class InsufficientVramError(RuntimeError):
    """Raised when a model exceeds total detected GPU VRAM."""


def query_nvidia_vram() -> Tuple[int, int]:
    """Return (total_mib, free_mib) for GPU 0 via nvidia-smi, or (0, 0)."""
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.free",
                "--format=csv,noheader,nounits",
                "-i",
                "0",
            ],
            text=True,
            timeout=3,
            creationflags=creationflags,
        ).strip()
        parts = [int(x.strip()) for x in out.splitlines()[0].split(",")]
        return parts[0], parts[1]
    except Exception:
        return 0, 0


@dataclass
class WorkerHandle:
    family: str
    pid: int
    real_pid: int
    port: int
    model_id: str
    device: str
    vram_est_mib: int
    started_at: float
    process: subprocess.Popen
    stderr_log: Path


@dataclass
class WorkerSupervisor:
    active_workers: Dict[str, WorkerHandle] = field(default_factory=dict)
    live_captions_active: bool = False

    def venv_python(self, family: str) -> Path:
        from .catalog_capabilities import resolve_runtime_envs_root

        base = resolve_runtime_envs_root(APP_ROOT) / family
        if sys.platform == "win32":
            return base / "Scripts" / "python.exe"
        return base / "bin" / "python"

    def worker_script(self, family: str) -> Path:
        return APP_ROOT / "backend" / "workers" / f"{family}_worker.py"

    def status_snapshot(self) -> dict:
        dead = [k for k, w in self.active_workers.items() if w.process.poll() is not None]
        for k in dead:
            self.active_workers.pop(k, None)

        families = {}
        for fam in ("qwen", "stt", "xtts", "f5", "fish", "kitten"):
            py = self.venv_python(fam)
            w = self.active_workers.get(fam)
            families[fam] = {
                "family": fam,
                "venv_ready": py.exists(),
                "script_ready": self.worker_script(fam).exists(),
                "running": w is not None,
                "pid": w.real_pid if w else None,
                "port": w.port if w else None,
                "model_id": w.model_id if w else None,
                "device": w.device if w else None,
                "vram_est_mib": w.vram_est_mib if w else 0,
                "started_at": w.started_at if w else None,
            }
        return {
            "workers": families,
            "live_captions_active": self.live_captions_active,
        }

    def ensure_vram_or_evict(
        self,
        target_family: str,
        device: str,
        vram_est_mib: int,
        free_vram_mib: int,
        total_vram_mib: int,
        force_stop_captions: bool = False,
    ) -> list[str]:
        """Check VRAM headroom; evict conflicting GPU workers or protect active Live Captions."""
        evicted: list[str] = []
        if device == "cpu":
            return evicted

        if total_vram_mib > 0 and vram_est_mib > total_vram_mib - 256:
            raise InsufficientVramError(
                f"Model requires ~{vram_est_mib} MiB, exceeding detected GPU VRAM ({total_vram_mib} MiB)."
            )

        if free_vram_mib >= vram_est_mib + 300:
            return evicted

        for fam, handle in list(self.active_workers.items()):
            if fam == target_family or handle.device != "gpu":
                continue
            if fam == "stt" and self.live_captions_active and not force_stop_captions:
                raise LiveCaptionsProtectedError(
                    "Live Captions is currently using GPU VRAM. Confirm stopping Live Captions to load TTS."
                )
            self.eject(fam)
            evicted.append(fam)
            if fam == "stt" and force_stop_captions:
                self.live_captions_active = False

        return evicted

    def ensure_venv(self, family: str) -> Path:
        py_exe = self.venv_python(family)
        if py_exe.exists():
            return py_exe
        req_file = APP_ROOT / "installer" / f"requirements-{family}.txt"
        import shutil

        uv_bin = shutil.which("uv")
        if not uv_bin or not req_file.is_file():
            raise FileNotFoundError(f"Worker venv not found: {py_exe}")

        env_dir = py_exe.parent.parent
        env_dir.parent.mkdir(parents=True, exist_ok=True)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            [uv_bin, "venv", str(env_dir), "--python", "3.12"],
            check=True,
            capture_output=True,
            text=True,
            creationflags=creationflags,
        )
        subprocess.run(
            [uv_bin, "pip", "install", "--python", str(py_exe), "-r", str(req_file)],
            check=True,
            capture_output=True,
            text=True,
            creationflags=creationflags,
        )
        return py_exe

    def spawn_worker(
        self,
        family: str,
        model_id: str,
        device: str,
        vram_est_mib: int,
        extra_args: Optional[list[str]] = None,
    ) -> WorkerHandle:
        if family in self.active_workers:
            self.eject(family)

        py_exe = self.ensure_venv(family)
        script = self.worker_script(family)
        if not py_exe.exists():
            raise FileNotFoundError(f"Worker venv not found: {py_exe}")
        if not script.exists():
            raise FileNotFoundError(f"Worker script not found: {script}")

        DEFAULT_TMP_DIR.mkdir(parents=True, exist_ok=True)
        stderr_log = DEFAULT_TMP_DIR / f"{family}_worker.stderr.log"
        err_fh = open(stderr_log, "w", encoding="utf-8")

        cmd = [str(py_exe), "-u", str(script), "--device", device]
        if extra_args:
            cmd.extend(extra_args)

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            cmd,
            cwd=str(APP_ROOT),
            stdout=subprocess.PIPE,
            stderr=err_fh,
            text=True,
            bufsize=1,
            creationflags=creationflags,
        )
        err_fh.close()

        deadline = time.time() + 30.0
        port = None
        real_pid = proc.pid
        while time.time() < deadline:
            assert proc.stdout is not None
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    err_txt = stderr_log.read_text(encoding="utf-8", errors="replace")[-1200:]
                    raise RuntimeError(f"{family} worker exited ({proc.returncode}): {err_txt}")
                time.sleep(0.05)
                continue
            s = line.strip()
            if s.startswith("{"):
                data = json.loads(s)
                port = int(data["port"])
                real_pid = int(data.get("pid", proc.pid))
                break

        if port is None:
            proc.kill()
            raise TimeoutError(f"Timed out waiting for port handshake from {family}_worker")

        # Keep draining worker stdout in background so logs never fill the pipe buffer and deadlock.
        if proc.stdout is not None:
            def _drain(pipe):
                try:
                    for _ in pipe:
                        pass
                except Exception:
                    pass

            threading.Thread(target=_drain, args=(proc.stdout,), daemon=True).start()

        handle = WorkerHandle(
            family=family,
            pid=proc.pid,
            real_pid=real_pid,
            port=port,
            model_id=model_id,
            device=device,
            vram_est_mib=vram_est_mib if device == "gpu" else 0,
            started_at=time.time(),
            process=proc,
            stderr_log=stderr_log,
        )
        self.active_workers[family] = handle
        return handle

    def eject(self, family: str) -> bool:
        handle = self.active_workers.pop(family, None)
        if not handle:
            return False
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if handle.real_pid and handle.real_pid != handle.pid:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(handle.real_pid)],
                capture_output=True,
                creationflags=creationflags,
            )
        if handle.process.poll() is None:
            handle.process.terminate()
            try:
                handle.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                handle.process.kill()
                handle.process.wait(timeout=4)
        if handle.process.stdout is not None:
            try:
                handle.process.stdout.close()
            except Exception:
                pass
        return True

    def shutdown_all(self) -> None:
        for fam in list(self.active_workers.keys()):
            self.eject(fam)
