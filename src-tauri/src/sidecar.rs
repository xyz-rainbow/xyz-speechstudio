use std::fs::{self, File};
use std::io::{BufRead, BufReader};
use std::mem::size_of;
use std::os::windows::io::AsRawHandle;
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use windows::Win32::Foundation::{CloseHandle, HANDLE};
use windows::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Serialize, Clone)]
pub struct BackendInfo {
    pub running: bool,
    pub port: u16,
    pub pid: u32,
    pub base_url: String,
}

#[derive(Deserialize)]
struct Handshake {
    port: u16,
    pid: u32,
}

#[derive(Deserialize)]
struct PartialSettings {
    api_fixed_port: Option<u16>,
    api_bind_host: Option<String>,
}

struct JobHandle(HANDLE);
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

pub struct BackendState {
    pub app_root: PathBuf,
    inner: Mutex<Option<RunningBackend>>,
}

struct RunningBackend {
    info: BackendInfo,
    child: Child,
    _job: JobHandle,
}

pub fn resolve_app_root() -> PathBuf {
    let mut seeds = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        seeds.push(exe);
    }
    if let Ok(cwd) = std::env::current_dir() {
        seeds.push(cwd);
    }
    for seed in seeds {
        let mut cur: Option<&Path> = Some(seed.as_path());
        while let Some(dir) = cur {
            if dir.join("backend").join("orchestrator").join("main.py").exists()
                && dir.join(".venvs").join("core").join("Scripts").join("python.exe").exists()
            {
                return dir.to_path_buf();
            }
            cur = dir.parent();
        }
    }
    PathBuf::from(r"Z:\[🛠️] [Tools]\xyz-speech-studio")
}

fn read_configured_network(app_root: &Path) -> (String, u16) {
    let path = app_root.join("data").join("settings.json");
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

impl BackendState {
    pub fn new() -> Self {
        Self {
            app_root: resolve_app_root(),
            inner: Mutex::new(None),
        }
    }

    pub fn start(&self) -> Result<BackendInfo, String> {
        let py_exe = self
            .app_root
            .join(".venvs")
            .join("core")
            .join("Scripts")
            .join("python.exe");
        if !py_exe.exists() {
            return Err(format!("Python core venv missing at {}", py_exe.display()));
        }

        let tmp_dir = self.app_root.join("data").join("tmp");
        let _ = fs::create_dir_all(&tmp_dir);
        let stderr_file = File::create(tmp_dir.join("orchestrator.stderr.log"))
            .map_err(|e| format!("Failed creating stderr log: {e}"))?;

        let (bind_host, fixed_port) = read_configured_network(&self.app_root);
        let port_arg = fixed_port.to_string();

        let job = unsafe {
            let h = CreateJobObjectW(None, None)
                .map_err(|e| format!("CreateJobObjectW failed: {e}"))?;
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
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
            JobHandle(h)
        };

        let mut child = Command::new(&py_exe)
            .current_dir(&self.app_root)
            .creation_flags(CREATE_NO_WINDOW)
            .args([
                "-u",
                "-m",
                "backend.orchestrator.main",
                "--host",
                &bind_host,
                "--port",
                &port_arg,
            ])
            .stdout(Stdio::piped())
            .stderr(Stdio::from(stderr_file))
            .spawn()
            .map_err(|e| format!("Failed spawning orchestrator: {e}"))?;

        unsafe {
            let child_handle = HANDLE(child.as_raw_handle() as *mut _);
            AssignProcessToJobObject(job.0, child_handle)
                .map_err(|e| format!("AssignProcessToJobObject failed: {e}"))?;
        }

        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "Missing orchestrator stdout".to_string())?;
        let mut reader = BufReader::new(stdout);
        let deadline = Instant::now() + Duration::from_secs(15);
        let mut handshake: Option<Handshake> = None;

        while Instant::now() < deadline {
            let mut line = String::new();
            match reader.read_line(&mut line) {
                Ok(0) => break,
                Ok(_) => {
                    let trimmed = line.trim();
                    if trimmed.starts_with('{') {
                        if let Ok(hs) = serde_json::from_str::<Handshake>(trimmed) {
                            handshake = Some(hs);
                            break;
                        }
                    }
                }
                Err(e) => return Err(format!("Failed reading orchestrator handshake: {e}")),
            }
        }

        let hs = handshake.ok_or_else(|| {
            let _ = child.kill();
            "Orchestrator exited or timed out before sending port handshake".to_string()
        })?;

        let info = BackendInfo {
            running: true,
            port: hs.port,
            pid: hs.pid,
            base_url: format!("http://127.0.0.1:{}", hs.port),
        };

        let mut guard = self.inner.lock().unwrap();
        *guard = Some(RunningBackend {
            info: info.clone(),
            child,
            _job: job,
        });
        Ok(info)
    }

    pub fn info(&self) -> BackendInfo {
        let mut guard = self.inner.lock().unwrap();
        if let Some(ref mut running) = *guard {
            if let Ok(Some(_)) = running.child.try_wait() {
                *guard = None;
            } else {
                return running.info.clone();
            }
        }
        BackendInfo {
            running: false,
            port: 0,
            pid: 0,
            base_url: String::new(),
        }
    }

    pub fn shutdown(&self) {
        let mut guard = self.inner.lock().unwrap();
        if let Some(mut running) = guard.take() {
            let _ = running.child.kill();
            let _ = running.child.wait();
        }
    }
}
