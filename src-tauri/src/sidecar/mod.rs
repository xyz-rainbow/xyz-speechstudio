use std::fs::{self, File};
use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Mutex};
use std::time::Duration;

use serde::{Deserialize, Serialize};

#[derive(Serialize, Clone)]
pub struct BackendInfo {
    pub running: bool,
    pub port: u16,
    pub pid: u32,
    pub base_url: String,
    pub live_captions_supported: bool,
    pub read_selection_supported: bool,
}

#[derive(Debug, Deserialize)]
struct Handshake {
    port: u16,
    pid: u32,
}

#[derive(Deserialize)]
struct PartialSettings {
    api_fixed_port: Option<u16>,
    api_bind_host: Option<String>,
}

pub struct BackendState {
    pub app_root: PathBuf,
    inner: Mutex<Option<RunningBackend>>,
}

struct RunningBackend {
    info: BackendInfo,
    child: Child,
    #[cfg(windows)]
    _job: windows_lifecycle::JobHandle,
    #[cfg(unix)]
    process_group_id: libc::pid_t,
}

fn core_venv_python(app_root: &Path) -> Option<PathBuf> {
    let bundled = app_root.join("runtime").join("python").join(
        if cfg!(windows) { "python.exe" } else { "bin/python3" }
    );
    if bundled.is_file() {
        return Some(bundled);
    }
    // Canonical: runtime/envs; legacy: .venvs (read fallback).
    let roots = [
        app_root.join("runtime").join("envs"),
        app_root.join(".venvs"),
    ];
    #[cfg(windows)]
    {
        for root in &roots {
            let path = root.join("core").join("Scripts").join("python.exe");
            if path.exists() {
                return Some(path);
            }
        }
    }
    #[cfg(not(windows))]
    {
        for root in &roots {
            let path = root.join("core").join("bin").join("python");
            if path.exists() {
                return Some(path);
            }
        }
    }
    None
}

fn looks_like_app_root(dir: &Path) -> bool {
    dir.join("backend")
        .join("orchestrator")
        .join("main.py")
        .exists()
        && core_venv_python(dir).is_some()
}

pub fn resolve_app_root() -> PathBuf {
    let mut seeds = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        #[cfg(target_os = "macos")]
        if let Some(contents) = exe.parent().and_then(|dir| dir.parent()) {
            seeds.push(contents.join("Resources"));
        }
        seeds.push(exe);
    }
    #[cfg(target_os = "linux")]
    {
        if let Some(app_dir) = std::env::var_os("APPDIR") {
            let base = PathBuf::from(app_dir).join("usr/lib");
            seeds.push(base.join("Speech Studio"));
            seeds.push(base.join("speech-studio"));
        }
        seeds.push(PathBuf::from("/usr/lib/Speech Studio"));
        seeds.push(PathBuf::from("/usr/lib/speech-studio"));
    }
    if let Ok(cwd) = std::env::current_dir() {
        seeds.push(cwd);
    }
    for seed in seeds {
        let mut cur: Option<&Path> = Some(seed.as_path());
        while let Some(dir) = cur {
            if looks_like_app_root(dir) {
                return dir.to_path_buf();
            }
            cur = dir.parent();
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn platform_caps() -> (bool, bool) {
    // (live_captions_supported, read_selection_supported)
    #[cfg(windows)]
    {
        (true, true)
    }
    #[cfg(target_os = "linux")]
    {
        (true, true)
    }
    #[cfg(target_os = "macos")]
    {
        (true, false)
    }
    #[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
    {
        (false, false)
    }
}

fn idle_backend_info() -> BackendInfo {
    let (live_captions_supported, read_selection_supported) = platform_caps();
    BackendInfo {
        running: false,
        port: 0,
        pid: 0,
        base_url: String::new(),
        live_captions_supported,
        read_selection_supported,
    }
}

fn read_configured_network(app_root: &Path) -> (String, u16) {
    let path = crate::paths::data_dir(app_root).join("settings.json");
    if let Ok(text) = fs::read_to_string(path) {
        if let Ok(parsed) = serde_json::from_str::<PartialSettings>(&text) {
            let host = match parsed.api_bind_host.as_deref() {
                Some("0.0.0.0") => "0.0.0.0".to_string(),
                _ => "127.0.0.1".to_string(),
            };
            return (host, parsed.api_fixed_port.unwrap_or(0));
        }
    }
    ("127.0.0.1".to_string(), 0)
}

fn read_handshake(child: &mut Child) -> Result<Handshake, String> {
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "Missing orchestrator stdout".to_string())?;
    wait_for_handshake(stdout, Duration::from_secs(15))
}

fn wait_for_handshake(stdout: impl Read + Send + 'static, timeout: Duration) -> Result<Handshake, String> {
    let (sender, receiver) = mpsc::channel();
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        loop {
            let mut line = String::new();
            match reader.read_line(&mut line) {
                Ok(0) => break,
                Ok(_) => {
                    if let Ok(hs) = serde_json::from_str::<Handshake>(line.trim()) {
                        if hs.port > 0 && hs.pid > 0 {
                            let _ = sender.send(Ok(hs));
                            // Keep draining stdout so later logs cannot block the backend.
                            let _ = std::io::copy(&mut reader, &mut std::io::sink());
                            return;
                        }
                    }
                }
                Err(error) => {
                    let _ = sender.send(Err(format!("Failed reading orchestrator handshake: {error}")));
                    return;
                }
            }
        }
        let _ = sender.send(Err("Orchestrator exited before sending port handshake".into()));
    });
    receiver.recv_timeout(timeout)
        .map_err(|_| "Orchestrator timed out before sending port handshake".to_string())?
}

impl BackendState {
    pub fn new() -> Self {
        Self {
            app_root: resolve_app_root(),
            inner: Mutex::new(None),
        }
    }

    pub fn start(&self) -> Result<BackendInfo, String> {
        let mut guard = self.inner.lock().unwrap();
        if let Some(running) = guard.as_mut() {
            if running.child.try_wait().map_err(|e| e.to_string())?.is_none() {
                return Ok(running.info.clone());
            }
        }
        if let Some(mut previous) = guard.take() {
            #[cfg(unix)]
            unix_lifecycle::kill_process_group(previous.process_group_id);
            let _ = previous.child.wait();
        }
        let py_exe = core_venv_python(&self.app_root)
            .ok_or_else(|| {
                "Python core runtime missing. Expected runtime/python (installer payload), or runtime/envs/core, or legacy .venvs/core.".to_string()
            })?;

        let data_dir = crate::paths::data_dir(&self.app_root);
        let cache_dir = crate::paths::cache_dir(&self.app_root);
        crate::paths::ensure_user_dirs(&data_dir, &cache_dir)
            .map_err(|e| format!("Failed creating data directory: {e}"))?;
        let tmp_dir = data_dir.join("tmp");
        let stderr_file = File::create(tmp_dir.join("orchestrator.stderr.log"))
            .map_err(|e| format!("Failed creating stderr log: {e}"))?;

        let (bind_host, fixed_port) = read_configured_network(&self.app_root);
        let port_arg = fixed_port.to_string();

        #[cfg(windows)]
        let job = windows_lifecycle::create_kill_on_close_job()?;

        let mut command = Command::new(&py_exe);
        command
            .current_dir(&self.app_root)
            .args([
                "-u",
                "-m",
                "backend.orchestrator.main",
                "--host",
                &bind_host,
                "--port",
                &port_arg,
            ])
            .env("SPEECHSTUDIO_DESKTOP", "1")
            .env("PYTHONUTF8", "1")
            .env("SPEECHSTUDIO_DATA_DIR", &data_dir)
            .env("SPEECHSTUDIO_CACHE_DIR", &cache_dir)
            .stdout(Stdio::piped())
            .stderr(Stdio::from(stderr_file));

        platform_spawn::configure_orchestrator_command(&mut command);

        let mut child = command
            .spawn()
            .map_err(|e| format!("Failed spawning orchestrator: {e}"))?;

        #[cfg(windows)]
        if let Err(error) = windows_lifecycle::assign_child_to_job(&job, &child) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }

        #[cfg(unix)]
        let process_group_id = child.id() as libc::pid_t;

        let hs = match read_handshake(&mut child) {
            Ok(handshake) => handshake,
            Err(error) => {
                #[cfg(unix)]
                unix_lifecycle::kill_process_group(process_group_id);
                let _ = child.kill();
                let _ = child.wait();
                return Err(error);
            }
        };

        let (live_captions_supported, read_selection_supported) = platform_caps();
        let info = BackendInfo {
            running: true,
            port: hs.port,
            pid: hs.pid,
            base_url: format!("http://127.0.0.1:{}", hs.port),
            live_captions_supported,
            read_selection_supported,
        };

        *guard = Some(RunningBackend {
            info: info.clone(),
            child,
            #[cfg(windows)]
            _job: job,
            #[cfg(unix)]
            process_group_id,
        });
        Ok(info)
    }

    pub fn info(&self) -> BackendInfo {
        let mut guard = self.inner.lock().unwrap();
        if let Some(mut running) = guard.take() {
            if let Ok(Some(_)) = running.child.try_wait() {
                #[cfg(unix)]
                unix_lifecycle::kill_process_group(running.process_group_id);
                let _ = running.child.wait();
            } else {
                let info = running.info.clone();
                *guard = Some(running);
                return info;
            }
        }
        idle_backend_info()
    }

    pub fn shutdown(&self) {
        let mut guard = self.inner.lock().unwrap();
        if let Some(mut running) = guard.take() {
            #[cfg(unix)]
            unix_lifecycle::kill_process_group(running.process_group_id);
            let _ = running.child.kill();
            let _ = running.child.wait();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn handshake_skips_logs_and_invalid_ports() {
        let data = b"starting\n{\"port\":0,\"pid\":42}\n{\"port\":1234,\"pid\":42}\n";
        let result = wait_for_handshake(Cursor::new(data), Duration::from_secs(1)).unwrap();
        assert_eq!(result.port, 1234);
        assert_eq!(result.pid, 42);
    }

    #[test]
    fn handshake_reports_early_exit() {
        assert!(wait_for_handshake(Cursor::new(b""), Duration::from_secs(1)).is_err());
    }

    #[test]
    fn silent_process_cannot_block_startup_forever() {
        struct BlockedReader(mpsc::Receiver<()>);
        impl Read for BlockedReader {
            fn read(&mut self, _: &mut [u8]) -> std::io::Result<usize> {
                let _ = self.0.recv();
                Ok(0)
            }
        }
        let (release, reader) = mpsc::channel();
        let result = wait_for_handshake(BlockedReader(reader), Duration::from_millis(20));
        drop(release);
        assert!(result.unwrap_err().contains("timed out"));
    }
}

#[cfg(windows)]
mod windows_lifecycle {
    use std::mem::size_of;
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;
    use windows::Win32::Foundation::{CloseHandle, HANDLE};
    use windows::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, JOB_OBJECT_LIMIT_BREAKAWAY_OK,
    };

    pub struct JobHandle(pub HANDLE);
    unsafe impl Send for JobHandle {}

    impl Drop for JobHandle {
        fn drop(&mut self) {
            if !self.0.is_invalid() {
                unsafe {
                    let _ = CloseHandle(self.0);
                }
            }
        }
    }

    pub fn create_kill_on_close_job() -> Result<JobHandle, String> {
        unsafe {
            let h = CreateJobObjectW(None, None)
                .map_err(|e| format!("CreateJobObjectW failed: {e}"))?;
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            // Kill the orchestrator and its non-breakaway children when the app exits.
            // BREAKAWAY_OK is intentional so optional GPU helpers can leave the job when required;
            // CrispASR/worker children should stay in-job unless they explicitly break away.
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK;
            SetInformationJobObject(
                h,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const _,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
            .map_err(|e| {
                let _ = CloseHandle(h);
                format!("SetInformationJobObject failed: {e}")
            })?;
            Ok(JobHandle(h))
        }
    }

    pub fn assign_child_to_job(job: &JobHandle, child: &Child) -> Result<(), String> {
        unsafe {
            let child_handle = HANDLE(child.as_raw_handle() as *mut _);
            AssignProcessToJobObject(job.0, child_handle)
                .map_err(|e| format!("AssignProcessToJobObject failed: {e}"))?;
        }
        Ok(())
    }
}

#[cfg(windows)]
mod platform_spawn {
    use std::os::windows::process::CommandExt;
    use std::process::Command;

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;

    pub fn configure_orchestrator_command(command: &mut Command) {
        command.creation_flags(CREATE_NO_WINDOW);
    }
}

#[cfg(unix)]
mod unix_lifecycle {
    pub fn kill_process_group(pgid: libc::pid_t) {
        if pgid > 0 {
            unsafe {
                let _ = libc::kill(-pgid, libc::SIGTERM);
                std::thread::sleep(std::time::Duration::from_millis(120));
                let _ = libc::kill(-pgid, libc::SIGKILL);
            }
        }
    }
}

#[cfg(unix)]
mod platform_spawn {
    use std::os::unix::process::CommandExt;
    use std::process::Command;

    pub fn configure_orchestrator_command(command: &mut Command) {
        command.process_group(0);
    }
}
