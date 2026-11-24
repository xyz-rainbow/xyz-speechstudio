use std::collections::HashMap;
use std::io::ErrorKind;
use std::mem::{size_of, zeroed};
use std::ptr::{self, null_mut};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter};
use tungstenite::{connect, Message};
use windows::Win32::Foundation::{CloseHandle, HANDLE, HWND, LPARAM};
use windows::Win32::Graphics::Dwm::{DwmGetWindowAttribute, DWMWA_CLOAKED};
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, GetClassNameW, GetWindowTextW, GetWindowThreadProcessId, IsWindowVisible,
};
use windows::Win32::Media::Audio::{
    ActivateAudioInterfaceAsync, IActivateAudioInterfaceAsyncOperation,
    IActivateAudioInterfaceCompletionHandler, IActivateAudioInterfaceCompletionHandler_Vtbl,
    IAudioCaptureClient, IAudioClient, IAudioSessionControl2, IAudioSessionManager2,
    IMMDeviceEnumerator, MMDeviceEnumerator, AUDIOCLIENT_ACTIVATION_PARAMS,
    AUDIOCLIENT_ACTIVATION_PARAMS_0, AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
    AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS, AUDCLNT_BUFFERFLAGS_SILENT, AUDCLNT_SHAREMODE_SHARED,
    AUDCLNT_STREAMFLAGS_LOOPBACK, eConsole, eRender, PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE,
    VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
};
use windows::Win32::System::Com::{
    CoCreateInstance, CoInitializeEx, CoTaskMemAlloc, CoTaskMemFree, BLOB, CLSCTX_ALL,
    COINIT_MULTITHREADED,
};
use windows::Win32::System::Com::StructuredStorage::{
    PROPVARIANT, PROPVARIANT_0, PROPVARIANT_0_0, PROPVARIANT_0_0_0,
};
use windows::Win32::System::Variant::VT_BLOB;
use windows::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W, TH32CS_SNAPPROCESS,
};
use windows::core::{IUnknown, Interface, BOOL, HRESULT};

const FRAME_SAMPLES: usize = 1600;
const WAVE_FORMAT_EXTENSIBLE: u16 = 0xFFFE;
const STOP_PARENTS: &[&str] = &[
    "explorer.exe",
    "svchost.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "sihost.exe",
    "runtimebroker.exe",
    "dwm.exe",
    "fontdrvhost.exe",
    "winlogon.exe",
];

use super::AudioApp;

struct Run {
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}

static RUN: Mutex<Option<Run>> = Mutex::new(None);

struct Ready {
    done: bool,
    raw: Option<*mut core::ffi::c_void>,
    error: Option<String>,
}

struct Handler {
    vtbl: *const IActivateAudioInterfaceCompletionHandler_Vtbl,
    refcount: std::sync::atomic::AtomicI32,
    slot: Mutex<Ready>,
    cv: Condvar,
}

fn emit_json(app: &AppHandle, payload: &str) {
    let _ = app.emit("caption", payload);
}

fn exe_from_entry(entry: &PROCESSENTRY32W) -> String {
    let len = entry
        .szExeFile
        .iter()
        .position(|c| *c == 0)
        .unwrap_or(entry.szExeFile.len());
    String::from_utf16_lossy(&entry.szExeFile[..len])
}

fn process_tree() -> HashMap<u32, (u32, String)> {
    let mut map = HashMap::new();
    unsafe {
        let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0).unwrap_or(HANDLE(null_mut()));
        if snap.0.is_null() {
            return map;
        }
        let mut entry: PROCESSENTRY32W = zeroed();
        entry.dwSize = size_of::<PROCESSENTRY32W>() as u32;
        if Process32FirstW(snap, &mut entry).is_ok() {
            loop {
                map.insert(
                    entry.th32ProcessID,
                    (entry.th32ParentProcessID, exe_from_entry(&entry)),
                );
                if Process32NextW(snap, &mut entry).is_err() {
                    break;
                }
            }
        }
        let _ = CloseHandle(snap);
    }
    map
}

fn is_stop_parent(name: &str) -> bool {
    STOP_PARENTS.iter().any(|stop| name.eq_ignore_ascii_case(stop))
}

fn is_shell_exe(name: &str) -> bool {
    matches!(
        name.to_ascii_lowercase().as_str(),
        "explorer.exe"
            | "searchhost.exe"
            | "startmenuexperiencehost.exe"
            | "shellexperiencehost.exe"
            | "textinputhost.exe"
            | "systemsettings.exe"
            | "applicationframehost.exe"
            | "lockapp.exe"
            | "sihost.exe"
            | "widgetboard.exe"
            | "widgets.exe"
            | "shellhost.exe"
            | "dwm.exe"
    )
}

fn skip_window_class(class: &str) -> bool {
    class.starts_with("IME")
        || class.starts_with("MSCTFIME")
        || class.starts_with("GDI+ Hook")
        || class.starts_with(".NET-BroadcastEventWindow")
        || class.starts_with("H.NotifyIcon")
        || class.starts_with("crashpad_")
        || matches!(
            class,
            "Progman" | "WorkerW" | "Shell_TrayWnd" | "DummyDWM" | "Base_PowerMessageWindow"
        )
}

/// Highest process of the same app. WebView2 hosts (WhatsApp) own the audio,
/// so a webview child climbs to that host. Capture includes the process tree.
fn app_root(pid: u32, tree: &HashMap<u32, (u32, String)>) -> u32 {
    let mut cur = pid;
    for _ in 0..16 {
        let Some((parent, name)) = tree.get(&cur) else {
            break;
        };
        if *parent == 0 || *parent == cur {
            break;
        }
        let Some((_, parent_name)) = tree.get(parent) else {
            break;
        };
        if is_stop_parent(parent_name) {
            break;
        }
        let webview = name.eq_ignore_ascii_case("msedgewebview2.exe");
        if parent_name.eq_ignore_ascii_case(name) || webview {
            cur = *parent;
            continue;
        }
        break;
    }
    cur
}

fn window_label(exe: &str, title: &str) -> String {
    let stem = exe
        .strip_suffix(".exe")
        .or_else(|| exe.strip_suffix(".EXE"))
        .unwrap_or(exe);
    let title = title.trim();
    if title.is_empty() || title.eq_ignore_ascii_case(stem) || title.eq_ignore_ascii_case(exe) {
        return stem.to_string();
    }
    let shown: String = title.chars().take(80).collect();
    format!("{stem} — {shown}")
}

struct ListedWindow {
    pid: u32,
    title: String,
    visible: bool,
}

struct WindowScan {
    tree: HashMap<u32, (u32, String)>,
    rows: Vec<ListedWindow>,
}

unsafe extern "system" fn enum_top_window(hwnd: HWND, lparam: LPARAM) -> BOOL {
    let ctx = &mut *(lparam.0 as *mut WindowScan);
    let mut class_buf = [0u16; 256];
    let class_len = GetClassNameW(hwnd, &mut class_buf).max(0) as usize;
    let class = String::from_utf16_lossy(&class_buf[..class_len.min(class_buf.len())]);
    if skip_window_class(&class) {
        return BOOL(1);
    }
    let mut text_buf = [0u16; 512];
    let text_len = GetWindowTextW(hwnd, &mut text_buf).max(0) as usize;
    if text_len == 0 {
        return BOOL(1);
    }
    let title = String::from_utf16_lossy(&text_buf[..text_len.min(text_buf.len())]);
    let title = title.trim();
    if title.is_empty() {
        return BOOL(1);
    }
    let visible = IsWindowVisible(hwnd).0 != 0;
    let winui = class == "WinUIDesktopWin32WindowClass";
    if !visible && !winui {
        return BOOL(1);
    }
    let mut cloaked = 0u32;
    if DwmGetWindowAttribute(
        hwnd,
        DWMWA_CLOAKED,
        &mut cloaked as *mut u32 as *mut core::ffi::c_void,
        size_of::<u32>() as u32,
    )
    .is_ok()
        && cloaked != 0
    {
        return BOOL(1);
    }
    let mut pid = 0u32;
    GetWindowThreadProcessId(hwnd, Some(&mut pid));
    if pid == 0 {
        return BOOL(1);
    }
    let root = app_root(pid, &ctx.tree);
    let exe = ctx
        .tree
        .get(&root)
        .map(|(_, name)| name.as_str())
        .unwrap_or("");
    if is_shell_exe(exe) {
        return BOOL(1);
    }
    ctx.rows.push(ListedWindow {
        pid: root,
        title: title.to_string(),
        visible,
    });
    BOOL(1)
}

#[tauri::command]
pub fn list_audio_apps() -> Result<Vec<AudioApp>, String> {
    unsafe {
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
        let enumerator: IMMDeviceEnumerator =
            CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL).map_err(|e| e.to_string())?;
        let device = enumerator
            .GetDefaultAudioEndpoint(eRender, eConsole)
            .map_err(|e| e.to_string())?;
        let manager: IAudioSessionManager2 = device
            .Activate(CLSCTX_ALL, None)
            .map_err(|e| e.to_string())?;
        let sessions = manager.GetSessionEnumerator().map_err(|e| e.to_string())?;
        let count = sessions.GetCount().map_err(|e| e.to_string())?;
        let mut scan = WindowScan {
            tree: process_tree(),
            rows: Vec::new(),
        };
        EnumWindows(Some(enum_top_window), LPARAM(&mut scan as *mut WindowScan as isize))
            .map_err(|e| e.to_string())?;
        let mut found: HashMap<u32, (String, bool)> = HashMap::new();
        for row in scan.rows {
            let exe = scan
                .tree
                .get(&row.pid)
                .map(|(_, name)| name.clone())
                .unwrap_or_default();
            let label = window_label(&exe, &row.title);
            match found.get(&row.pid) {
                Some((_, visible)) if *visible && !row.visible => {}
                Some((current, visible))
                    if *visible == row.visible && current.chars().count() >= label.chars().count() => {}
                _ => {
                    found.insert(row.pid, (label, row.visible));
                }
            }
        }
        for index in 0..count {
            let Ok(control) = sessions.GetSession(index) else {
                continue;
            };
            let Ok(control2) = control.cast::<IAudioSessionControl2>() else {
                continue;
            };
            if control2.IsSystemSoundsSession().0 == 0 {
                continue;
            }
            let Ok(pid) = control2.GetProcessId() else {
                continue;
            };
            if pid == 0 {
                continue;
            }
            let root = app_root(pid, &scan.tree);
            if found.contains_key(&root) {
                continue;
            }
            let exe = scan
                .tree
                .get(&root)
                .map(|(_, name)| name.clone())
                .filter(|name| !name.is_empty() && !is_shell_exe(name))
                .unwrap_or_else(|| format!("pid {root}"));
            found.insert(root, (window_label(&exe, ""), false));
        }
        let mut apps: Vec<AudioApp> = found
            .into_iter()
            .map(|(pid, (name, _))| AudioApp { pid, name })
            .collect();
        apps.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
        Ok(apps)
    }
}

unsafe extern "system" fn handler_query(
    this: *mut core::ffi::c_void,
    iid: *const windows::core::GUID,
    out: *mut *mut core::ffi::c_void,
) -> HRESULT {
    if iid.is_null() || out.is_null() {
        return HRESULT(0x80070057u32 as i32);
    }
    let iid = *iid;
    if iid == IUnknown::IID || iid == IActivateAudioInterfaceCompletionHandler::IID {
        handler_add(this);
        *out = this;
        HRESULT(0)
    } else {
        *out = null_mut();
        HRESULT(0x80004002u32 as i32)
    }
}

unsafe extern "system" fn handler_add(this: *mut core::ffi::c_void) -> u32 {
    let handler = &*(this as *const Handler);
    handler.refcount.fetch_add(1, Ordering::SeqCst) as u32 + 1
}

unsafe extern "system" fn handler_release(this: *mut core::ffi::c_void) -> u32 {
    let handler = &*(this as *const Handler);
    let prev = handler.refcount.fetch_sub(1, Ordering::SeqCst);
    if prev == 1 {
        drop(Box::from_raw(this as *mut Handler));
        0
    } else {
        (prev - 1) as u32
    }
}

unsafe extern "system" fn handler_completed(
    this: *mut core::ffi::c_void,
    operation: *mut core::ffi::c_void,
) -> HRESULT {
    let handler = &*(this as *const Handler);
    let mut ready = handler.slot.lock().unwrap();
    if operation.is_null() {
        ready.error = Some("WASAPI activation returned no operation".into());
    } else if let Some(op) =
        IActivateAudioInterfaceAsyncOperation::from_raw_borrowed(&operation)
    {
        let mut hr = HRESULT(0);
        let mut unknown: Option<IUnknown> = None;
        if op.GetActivateResult(&mut hr, &mut unknown).is_err() || hr.0 < 0 {
            ready.error = Some(format!("WASAPI activation failed ({})", hr.0));
        } else if let Some(unknown) = unknown {
            ready.raw = Some(unknown.as_raw());
            std::mem::forget(unknown);
        } else {
            ready.error = Some("WASAPI activation returned no audio client".into());
        }
    }
    ready.done = true;
    handler.cv.notify_one();
    HRESULT(0)
}

static HANDLER_VTBL: IActivateAudioInterfaceCompletionHandler_Vtbl =
    IActivateAudioInterfaceCompletionHandler_Vtbl {
        base__: windows::core::IUnknown_Vtbl {
            QueryInterface: handler_query,
            AddRef: handler_add,
            Release: handler_release,
        },
        ActivateCompleted: handler_completed,
    };

fn activate_loopback(pid: u32) -> Result<IAudioClient, String> {
    let params = AUDIOCLIENT_ACTIVATION_PARAMS {
        ActivationType: AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
        Anonymous: AUDIOCLIENT_ACTIVATION_PARAMS_0 {
            ProcessLoopbackParams: AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS {
                TargetProcessId: pid,
                ProcessLoopbackMode: PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE,
            },
        },
    };
    let bytes = size_of::<AUDIOCLIENT_ACTIVATION_PARAMS>();
    let blob = unsafe { CoTaskMemAlloc(bytes) as *mut u8 };
    if blob.is_null() {
        return Err("CoTaskMemAlloc failed".into());
    }
    unsafe {
        ptr::copy_nonoverlapping(&params as *const _ as *const u8, blob, bytes);
    }
    let prop = unsafe {
        let mut value = zeroed::<PROPVARIANT_0_0_0>();
        value.blob = BLOB {
            cbSize: bytes as u32,
            pBlobData: blob,
        };
        PROPVARIANT {
            Anonymous: PROPVARIANT_0 {
                Anonymous: std::mem::ManuallyDrop::new(PROPVARIANT_0_0 {
                    vt: VT_BLOB,
                    wReserved1: 0,
                    wReserved2: 0,
                    wReserved3: 0,
                    Anonymous: value,
                }),
            },
        }
    };

    let handler = Box::new(Handler {
        vtbl: &HANDLER_VTBL,
        refcount: std::sync::atomic::AtomicI32::new(1),
        slot: Mutex::new(Ready {
            done: false,
            raw: None,
            error: None,
        }),
        cv: Condvar::new(),
    });
    let raw_handler = Box::into_raw(handler);
    let iface = unsafe {
        IActivateAudioInterfaceCompletionHandler::from_raw(raw_handler as *mut core::ffi::c_void)
    };
    let operation = unsafe {
        ActivateAudioInterfaceAsync(
            VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
            &IAudioClient::IID,
            Some(&prop as *const PROPVARIANT),
            &iface,
        )
        .map_err(|e| e.to_string())?
    };
    let (client_ptr, error, still_pending) = {
        let handler_ref = unsafe { &*raw_handler };
        debug_assert!(!handler_ref.vtbl.is_null());
        let mut ready = handler_ref.slot.lock().unwrap();
        let wait = handler_ref
            .cv
            .wait_timeout_while(ready, Duration::from_secs(4), |slot| !slot.done)
            .map_err(|_| "activation wait poisoned".to_string())?;
        ready = wait.0;
        if wait.1.timed_out() && !ready.done {
            (
                None,
                Some("WASAPI activation timed out".to_string()),
                true,
            )
        } else {
            (ready.raw.take(), ready.error.clone(), false)
        }
    };
    if still_pending {
        // The completion callback may still arrive. Freeing the handler here
        // would let that callback touch freed memory.
        std::mem::forget(operation);
        std::mem::forget(iface);
    } else {
        drop(operation);
        drop(iface);
    }
    let _ = params;
    match client_ptr {
        Some(ptr) => Ok(unsafe { IAudioClient::from_raw(ptr) }),
        None => Err(error.unwrap_or_else(|| "WASAPI activation failed".into())),
    }
}

struct Resampler {
    src_rate: u32,
    src: Vec<f32>,
    pos: f64,
    out: Vec<i16>,
}

impl Resampler {
    fn new(src_rate: u32) -> Self {
        Self {
            src_rate: src_rate.max(1),
            src: Vec::new(),
            pos: 0.0,
            out: Vec::new(),
        }
    }

    fn push_mono(&mut self, samples: &[f32]) -> Vec<Vec<u8>> {
        self.src.extend_from_slice(samples);
        let step = self.src_rate as f64 / 16000.0;
        while self.pos + 1.0 < self.src.len() as f64 {
            let index = self.pos.floor() as usize;
            let frac = (self.pos - index as f64) as f32;
            let sample = self.src[index] * (1.0 - frac) + self.src[index + 1] * frac;
            self.out
                .push((sample.clamp(-1.0, 1.0) * 32767.0) as i16);
            self.pos += step;
        }
        let drop_n = self.pos.floor() as usize;
        if drop_n > 0 && drop_n <= self.src.len() {
            self.src.drain(..drop_n);
            self.pos -= drop_n as f64;
        }
        let mut frames = Vec::new();
        while self.out.len() >= FRAME_SAMPLES {
            let frame: Vec<i16> = self.out.drain(..FRAME_SAMPLES).collect();
            let bytes: Vec<u8> = frame.iter().flat_map(|s| s.to_le_bytes()).collect();
            frames.push(bytes);
        }
        frames
    }
}

fn sample_to_f32(format_tag: u16, bits: u16, data: *const u8) -> f32 {
    unsafe {
        if bits >= 32 || format_tag == 3 {
            *data.cast::<f32>()
        } else {
            *data.cast::<i16>() as f32 / 32768.0
        }
    }
}

fn capture_loop(
    app: AppHandle,
    pid: u32,
    ws_url: String,
    language: String,
    stop: Arc<AtomicBool>,
) {
    let result = (|| -> Result<(), String> {
        unsafe {
            let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
        }
        let client = activate_loopback(pid)?;
        let format_ptr = unsafe { client.GetMixFormat().map_err(|e| e.to_string())? };
        let format = unsafe { &*format_ptr };
        let channels = format.nChannels.max(1) as usize;
        let rate = format.nSamplesPerSec.max(1);
        let bits = format.wBitsPerSample;
        let block = format.nBlockAlign as usize;
        let tag = if format.wFormatTag == WAVE_FORMAT_EXTENSIBLE {
            let sub = unsafe {
                std::ptr::addr_of!(
                    (*(format_ptr as *const windows::Win32::Media::Audio::WAVEFORMATEXTENSIBLE)).SubFormat
                )
                .read_unaligned()
                .to_u128()
            };
            if sub >> 96 == 3 { 3 } else { 1 }
        } else {
            format.wFormatTag
        };
        let init = unsafe {
            client.Initialize(
                AUDCLNT_SHAREMODE_SHARED,
                AUDCLNT_STREAMFLAGS_LOOPBACK,
                0,
                0,
                format_ptr,
                None,
            )
        };
        if init.is_err() {
            unsafe {
                client
                    .Initialize(AUDCLNT_SHAREMODE_SHARED, 0, 0, 0, format_ptr, None)
                    .map_err(|e| e.to_string())?;
            }
        }
        unsafe { CoTaskMemFree(Some(format_ptr as *const _)) };
        let capture: IAudioCaptureClient = unsafe { client.GetService().map_err(|e| e.to_string())? };
        unsafe { client.Start().map_err(|e| e.to_string())? };

        let (mut socket, _) = connect(ws_url.as_str()).map_err(|e| e.to_string())?;
        match socket.get_mut() {
            tungstenite::stream::MaybeTlsStream::Plain(stream) => {
                stream
                    .set_read_timeout(Some(Duration::from_millis(40)))
                    .map_err(|e| e.to_string())?;
            }
            _ => {}
        }
        socket
            .send(Message::Text(format!(
                "{{\"type\":\"start\",\"language\":{}}}",
                serde_json::to_string(&language).unwrap_or_else(|_| "\"auto\"".into())
            )))
            .map_err(|e| e.to_string())?;
        let socket = Arc::new(Mutex::new(socket));
        let reader_stop = stop.clone();
        let reader_app = app.clone();
        let reader_socket = socket.clone();
        let reader = thread::spawn(move || loop {
            if reader_stop.load(Ordering::SeqCst) {
                break;
            }
            let msg = {
                let mut sock = reader_socket.lock().unwrap();
                sock.read()
            };
            match msg {
                Ok(Message::Text(text)) => emit_json(&reader_app, &text),
                Ok(Message::Close(_)) => break,
                Err(tungstenite::Error::Io(err))
                    if err.kind() == ErrorKind::TimedOut || err.kind() == ErrorKind::WouldBlock => {}
                Err(_) => break,
                _ => {}
            }
        });

        let mut resampler = Resampler::new(rate);
        while !stop.load(Ordering::SeqCst) {
            let frames = unsafe { capture.GetNextPacketSize().unwrap_or(0) };
            if frames == 0 {
                thread::sleep(Duration::from_millis(5));
                continue;
            }
            let mut data = null_mut();
            let mut count = 0u32;
            let mut flags = 0u32;
            if unsafe {
                capture
                    .GetBuffer(&mut data, &mut count, &mut flags, None, None)
                    .is_err()
            } {
                break;
            }
            let mut mono = Vec::with_capacity(count as usize);
            if flags & AUDCLNT_BUFFERFLAGS_SILENT.0 as u32 == 0 && !data.is_null() && block > 0 {
                for frame in 0..count as usize {
                    let mut sum = 0.0f32;
                    for channel in 0..channels {
                        let offset = frame * block + channel * (bits as usize / 8).max(2);
                        sum += sample_to_f32(tag, bits, unsafe { data.add(offset) });
                    }
                    mono.push(sum / channels as f32);
                }
            } else {
                mono.resize(count as usize, 0.0);
            }
            unsafe { capture.ReleaseBuffer(count).ok() };
            for frame in resampler.push_mono(&mono) {
                let mut sock = socket.lock().unwrap();
                if sock.send(Message::Binary(frame)).is_err() {
                    stop.store(true, Ordering::SeqCst);
                    break;
                }
            }
        }
        unsafe { client.Stop().ok() };
        {
            let mut sock = socket.lock().unwrap();
            let _ = sock.send(Message::Text("{\"type\":\"stop\"}".into()));
            let _ = sock.close(None);
        }
        stop.store(true, Ordering::SeqCst);
        let _ = reader.join();
        Ok(())
    })();
    if let Err(err) = result {
        let payload = serde_json::json!({"type": "error", "text": err}).to_string();
        emit_json(&app, &payload);
    }
}

#[tauri::command]
pub fn start_live_captions(
    app: AppHandle,
    pid: u32,
    ws_url: String,
    language: String,
) -> Result<(), String> {
    if pid == 0 {
        return Err("Pick an application first".into());
    }
    stop_live_captions()?;
    let stop = Arc::new(AtomicBool::new(false));
    let thread_stop = stop.clone();
    let thread = thread::spawn(move || capture_loop(app, pid, ws_url, language, thread_stop));
    *RUN.lock().unwrap() = Some(Run {
        stop,
        thread: Some(thread),
    });
    Ok(())
}

#[tauri::command]
pub fn stop_live_captions() -> Result<(), String> {
    let mut run = RUN.lock().unwrap();
    if let Some(mut current) = run.take() {
        current.stop.store(true, Ordering::SeqCst);
        if let Some(thread) = current.thread.take() {
            drop(run);
            let _ = thread.join();
            return Ok(());
        }
    }
    Ok(())
}
