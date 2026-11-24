use std::collections::HashMap;
use std::env;
use std::mem::{size_of, ManuallyDrop};
use std::os::windows::io::AsRawHandle;
use std::process::Command;
use std::sync::{Arc, Condvar, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use nvml_wrapper::Nvml;
use serde::Serialize;
use windows::core::{implement, Interface, Result as WinResult, HRESULT, PROPVARIANT};
use windows_core::imp::{
    BLOB, PROPVARIANT as RawPropVariant, PROPVARIANT_0, PROPVARIANT_0_0, PROPVARIANT_0_0_0,
};
use windows::Win32::Foundation::{CloseHandle, HANDLE, STILL_ACTIVE};
use windows::Win32::Media::Audio::{
    eConsole, eRender, ActivateAudioInterfaceAsync, IActivateAudioInterfaceAsyncOperation,
    IActivateAudioInterfaceCompletionHandler, IActivateAudioInterfaceCompletionHandler_Impl,
    IAudioCaptureClient, IAudioClient, IAudioSessionControl2, IAudioSessionManager2,
    IMMDeviceEnumerator, MMDeviceEnumerator, AUDCLNT_BUFFERFLAGS_SILENT,
    AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM, AUDCLNT_STREAMFLAGS_LOOPBACK,
    AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY, AUDIOCLIENT_ACTIVATION_PARAMS,
    AUDIOCLIENT_ACTIVATION_PARAMS_0, AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
    AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS, PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE,
    VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, WAVEFORMATEX,
};
use windows::Win32::System::Com::{
    CoInitializeEx, CoUninitialize, IAgileObject, IAgileObject_Impl, CLSCTX_ALL, COINIT_MULTITHREADED,
};
use windows::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W, TH32CS_SNAPPROCESS,
};
use windows::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};
use windows::Win32::System::Threading::{
    GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
};
use windows::Win32::System::Variant::VT_BLOB;

const WAVE_FORMAT_IEEE_FLOAT_TAG: u16 = 3;

#[derive(Serialize)]
struct VramInfo {
    gpu: String,
    total_mib: u64,
    used_mib: u64,
    free_mib: u64,
}

#[derive(Serialize)]
struct ProcessSummary {
    pid: u32,
    parent_pid: u32,
    root_pid: u32,
    exe: String,
}

#[derive(Serialize)]
struct AudioSessionInfo {
    pid: u32,
    root_pid: u32,
    exe: String,
    state: i32,
    display_name: String,
}

#[derive(Serialize)]
struct SessionsReport {
    audio_sessions: Vec<AudioSessionInfo>,
    target_apps: Vec<ProcessSummary>,
}

#[derive(Serialize)]
struct LoopbackReport {
    status: String,
    input_pid: u32,
    root_pid: u32,
    exe: String,
    frames: u64,
    non_silent_frames: u64,
    rms: f64,
    peak: f32,
}

fn cmd_nvml() -> Result<(), Box<dyn std::error::Error>> {
    let nvml = Nvml::init()?;
    let dev = nvml.device_by_index(0)?;
    let name = dev.name()?;
    let mem = dev.memory_info()?;
    let info = VramInfo {
        gpu: name,
        total_mib: mem.total / (1024 * 1024),
        used_mib: mem.used / (1024 * 1024),
        free_mib: mem.free / (1024 * 1024),
    };
    println!("{}", serde_json::to_string(&info)?);
    Ok(())
}

fn cmd_job_test() -> Result<(), Box<dyn std::error::Error>> {
    unsafe {
        let job = CreateJobObjectW(None, None)?;
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &limits as *const _ as *const _,
            size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        )?;

        let mut child = Command::new("cmd")
            .args(["/c", "ping -n 30 127.0.0.1 >nul"])
            .spawn()?;
        let child_pid = child.id();
        let child_handle = HANDLE(child.as_raw_handle() as *mut _);
        AssignProcessToJobObject(job, child_handle)?;

        // Confirm child is currently running
        let probe = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, child_pid)?;
        let mut code: u32 = 0;
        GetExitCodeProcess(probe, &mut code)?;
        let _ = CloseHandle(probe);
        if code != STILL_ACTIVE.0 as u32 {
            return Err(format!("child exited prematurely with code {code}").into());
        }

        // Close job handle -> Windows should terminate child immediately
        CloseHandle(job)?;
        thread::sleep(Duration::from_millis(400));

        let exited = match OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, child_pid) {
            Err(_) => true,
            Ok(h) => {
                let mut post_code: u32 = 0;
                let ok = GetExitCodeProcess(h, &mut post_code).is_ok();
                let _ = CloseHandle(h);
                !ok || post_code != STILL_ACTIVE.0 as u32
            }
        };

        let _ = child.try_wait();
        if !exited {
            let _ = child.kill();
            return Err("child remained alive after closing Job Object".into());
        }
        println!("JOB_OBJECT_OK child_pid={child_pid}");
    }
    Ok(())
}

fn snapshot_processes() -> Result<HashMap<u32, (u32, String)>, Box<dyn std::error::Error>> {
    let mut map = HashMap::new();
    unsafe {
        let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)?;
        let mut entry = PROCESSENTRY32W {
            dwSize: size_of::<PROCESSENTRY32W>() as u32,
            ..Default::default()
        };
        if Process32FirstW(snap, &mut entry).is_ok() {
            loop {
                let len = entry
                    .szExeFile
                    .iter()
                    .position(|&c| c == 0)
                    .unwrap_or(entry.szExeFile.len());
                let exe = String::from_utf16_lossy(&entry.szExeFile[..len]);
                map.insert(entry.th32ProcessID, (entry.th32ParentProcessID, exe));
                if Process32NextW(snap, &mut entry).is_err() {
                    break;
                }
            }
        }
        let _ = CloseHandle(snap);
    }
    Ok(map)
}

fn resolve_root_pid(map: &HashMap<u32, (u32, String)>, pid: u32) -> (u32, String) {
    let Some((_, exe)) = map.get(&pid) else {
        return (pid, String::new());
    };
    let target_lower = exe.to_lowercase();
    let mut cur = pid;
    let mut steps = 0;
    while steps < 32 {
        steps += 1;
        let Some(&(ppid, _)) = map.get(&cur) else {
            break;
        };
        if ppid == 0 || ppid == cur {
            break;
        }
        if let Some((_, pexe)) = map.get(&ppid) {
            if pexe.to_lowercase() == target_lower {
                cur = ppid;
                continue;
            }
        }
        break;
    }
    (cur, exe.clone())
}

fn cmd_sessions() -> Result<(), Box<dyn std::error::Error>> {
    let proc_map = snapshot_processes()?;
    let mut target_apps = Vec::new();
    for (&pid, &(ppid, ref exe)) in &proc_map {
        let lower = exe.to_lowercase();
        if lower == "discord.exe" || lower == "msedge.exe" || lower == "chrome.exe" {
            let (root_pid, _) = resolve_root_pid(&proc_map, pid);
            target_apps.push(ProcessSummary {
                pid,
                parent_pid: ppid,
                root_pid,
                exe: exe.clone(),
            });
        }
    }
    target_apps.sort_by_key(|p| (p.exe.clone(), p.root_pid, p.pid));

    let mut audio_sessions = Vec::new();
    unsafe {
        let hr = CoInitializeEx(None, COINIT_MULTITHREADED);
        if hr.is_err() {
            return Err(format!("CoInitializeEx failed: {hr:?}").into());
        }
        let res = (|| -> Result<(), Box<dyn std::error::Error>> {
            let enumerator: IMMDeviceEnumerator =
                windows::Win32::System::Com::CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL)?;
            let device = enumerator.GetDefaultAudioEndpoint(eRender, eConsole)?;
            let mgr: IAudioSessionManager2 = device.Activate(CLSCTX_ALL, None)?;
            let session_enum = mgr.GetSessionEnumerator()?;
            let count = session_enum.GetCount()?;
            for i in 0..count {
                let ctrl = session_enum.GetSession(i)?;
                let state = ctrl.GetState().map(|s| s.0).unwrap_or(-1);
                let display_name = ctrl
                    .GetDisplayName()
                    .ok()
                    .map(|pw| {
                        let s = pw.to_string().unwrap_or_default();
                        windows::Win32::System::Com::CoTaskMemFree(Some(pw.0 as *const _));
                        s
                    })
                    .unwrap_or_default();
                if let Ok(ctrl2) = ctrl.cast::<IAudioSessionControl2>() {
                    let pid = ctrl2.GetProcessId().unwrap_or(0);
                    let (root_pid, exe) = resolve_root_pid(&proc_map, pid);
                    audio_sessions.push(AudioSessionInfo {
                        pid,
                        root_pid,
                        exe,
                        state,
                        display_name,
                    });
                }
            }
            Ok(())
        })();
        CoUninitialize();
        res?;
    }

    let report = SessionsReport {
        audio_sessions,
        target_apps,
    };
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(())
}

#[implement(IActivateAudioInterfaceCompletionHandler, IAgileObject)]
struct ActivationHandler {
    state: Arc<(Mutex<Option<WinResult<IAudioClient>>>, Condvar)>,
}

impl IAgileObject_Impl for ActivationHandler_Impl {}

impl IActivateAudioInterfaceCompletionHandler_Impl for ActivationHandler_Impl {
    fn ActivateCompleted(
        &self,
        operation: Option<&IActivateAudioInterfaceAsyncOperation>,
    ) -> WinResult<()> {
        let result = (|| -> WinResult<IAudioClient> {
            let op = operation.ok_or_else(|| windows::core::Error::from(HRESULT(-1)))?;
            let mut hr = HRESULT(0);
            let mut iface = None;
            unsafe { op.GetActivateResult(&mut hr, &mut iface)? };
            hr.ok()?;
            let unk = iface.ok_or_else(|| windows::core::Error::from(HRESULT(-1)))?;
            unk.cast::<IAudioClient>()
        })();

        let (lock, cv) = &*self.state;
        let mut guard = lock.lock().unwrap();
        *guard = Some(result);
        cv.notify_all();
        Ok(())
    }
}

fn cmd_loopback(pid: u32, seconds: f64) -> Result<(), Box<dyn std::error::Error>> {
    let proc_map = snapshot_processes()?;
    let (root_pid, exe) = resolve_root_pid(&proc_map, pid);

    unsafe {
        let hr = CoInitializeEx(None, COINIT_MULTITHREADED);
        if hr.is_err() {
            return Err(format!("CoInitializeEx failed: {hr:?}").into());
        }

        let res = (|| -> Result<LoopbackReport, Box<dyn std::error::Error>> {
            let mut params = AUDIOCLIENT_ACTIVATION_PARAMS {
                ActivationType: AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
                Anonymous: AUDIOCLIENT_ACTIVATION_PARAMS_0 {
                    ProcessLoopbackParams: AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS {
                        TargetProcessId: root_pid,
                        ProcessLoopbackMode: PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE,
                    },
                },
            };

            let prop = ManuallyDrop::new(PROPVARIANT::from_raw(RawPropVariant {
                Anonymous: PROPVARIANT_0 {
                    Anonymous: PROPVARIANT_0_0 {
                        vt: VT_BLOB.0,
                        wReserved1: 0,
                        wReserved2: 0,
                        wReserved3: 0,
                        Anonymous: PROPVARIANT_0_0_0 {
                            blob: BLOB {
                                cbSize: size_of::<AUDIOCLIENT_ACTIVATION_PARAMS>() as u32,
                                pBlobData: &mut params as *mut _ as *mut u8,
                            },
                        },
                    },
                },
            }));

            let state = Arc::new((Mutex::new(None), Condvar::new()));
            let handler: IActivateAudioInterfaceCompletionHandler = ActivationHandler {
                state: Arc::clone(&state),
            }
            .into();

            let _op = ActivateAudioInterfaceAsync(
                VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
                &IAudioClient::IID,
                Some(&*prop as *const PROPVARIANT),
                &handler,
            )?;

            let (lock, cv) = &*state;
            let mut guard = lock.lock().unwrap();
            while guard.is_none() {
                guard = cv.wait(guard).unwrap();
            }
            let client = guard.take().unwrap()?;

            let channels: u16 = 1;
            let sample_rate: u32 = 16000;
            let bits: u16 = 32;
            let block_align = channels * (bits / 8);
            let wfx = WAVEFORMATEX {
                wFormatTag: WAVE_FORMAT_IEEE_FLOAT_TAG,
                nChannels: channels,
                nSamplesPerSec: sample_rate,
                nAvgBytesPerSec: sample_rate * (block_align as u32),
                nBlockAlign: block_align,
                wBitsPerSample: bits,
                cbSize: 0,
            };

            let flags = AUDCLNT_STREAMFLAGS_LOOPBACK
                | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM
                | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY;
            client.Initialize(AUDCLNT_SHAREMODE_SHARED, flags, 200_000, 0, &wfx, None)?;
            let capture: IAudioCaptureClient = client.GetService()?;
            client.Start()?;

            let start = Instant::now();
            let target_dur = Duration::from_secs_f64(seconds.max(0.5));
            let mut total_frames: u64 = 0;
            let mut non_silent_frames: u64 = 0;
            let mut sum_sq: f64 = 0.0;
            let mut peak: f32 = 0.0;

            while start.elapsed() < target_dur {
                loop {
                    let packet_len = capture.GetNextPacketSize()?;
                    if packet_len == 0 {
                        break;
                    }
                    let mut data_ptr: *mut u8 = std::ptr::null_mut();
                    let mut num_frames: u32 = 0;
                    let mut buf_flags: u32 = 0;
                    capture.GetBuffer(
                        &mut data_ptr,
                        &mut num_frames,
                        &mut buf_flags,
                        None,
                        None,
                    )?;
                    total_frames += num_frames as u64;
                    let is_silent = (buf_flags & (AUDCLNT_BUFFERFLAGS_SILENT.0 as u32)) != 0;
                    if !is_silent && !data_ptr.is_null() && num_frames > 0 {
                        let samples = std::slice::from_raw_parts(
                            data_ptr as *const f32,
                            (num_frames as usize) * (channels as usize),
                        );
                        let mut frame_has_signal = false;
                        for &s in samples {
                            let a = s.abs();
                            if a > 1e-5 {
                                frame_has_signal = true;
                            }
                            if a > peak {
                                peak = a;
                            }
                            sum_sq += (s as f64) * (s as f64);
                        }
                        if frame_has_signal {
                            non_silent_frames += num_frames as u64;
                        }
                    }
                    capture.ReleaseBuffer(num_frames)?;
                }
                thread::sleep(Duration::from_millis(10));
            }

            client.Stop()?;
            let rms = if total_frames > 0 {
                (sum_sq / (total_frames as f64 * channels as f64)).sqrt()
            } else {
                0.0
            };

            Ok(LoopbackReport {
                status: "LOOPBACK_OK".to_string(),
                input_pid: pid,
                root_pid,
                exe,
                frames: total_frames,
                non_silent_frames,
                rms,
                peak,
            })
        })();

        CoUninitialize();
        let report = res?;
        println!("{}", serde_json::to_string(&report)?);
    }
    Ok(())
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: rust_spike <nvml|job-test|sessions|loopback <pid> [seconds]>");
        std::process::exit(1);
    }
    let res = match args[1].as_str() {
        "nvml" => cmd_nvml(),
        "job-test" => cmd_job_test(),
        "sessions" => cmd_sessions(),
        "loopback" => {
            if args.len() < 3 {
                Err("loopback requires <pid>".into())
            } else {
                let pid: u32 = args[2].parse().expect("invalid pid");
                let secs: f64 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(3.0);
                cmd_loopback(pid, secs)
            }
        }
        other => Err(format!("unknown subcommand: {other}").into()),
    };
    if let Err(e) = res {
        eprintln!("ERROR: {e}");
        std::process::exit(1);
    }
}
