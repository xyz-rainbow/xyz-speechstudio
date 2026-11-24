use std::collections::{HashMap, HashSet};
use std::io::ErrorKind;
use std::mem::{size_of, zeroed};
use std::ptr::{self, null_mut};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use tauri::{AppHandle, Emitter};
use tungstenite::{connect, Message};
use windows::core::{IUnknown, Interface, BOOL, HRESULT};
use windows::Win32::Foundation::{CloseHandle, HANDLE, HWND, LPARAM, RECT, WPARAM};
use windows::Win32::Graphics::Dwm::{DwmGetWindowAttribute, DWMWA_CLOAKED};
use windows::Win32::Graphics::Gdi::{
    CreateCompatibleDC, CreateDIBSection, DeleteDC, DeleteObject, SelectObject, SetStretchBltMode,
    StretchBlt, BITMAPINFO, BITMAPINFOHEADER, BI_RGB, DIB_RGB_COLORS, HALFTONE, HDC, HGDIOBJ,
    SRCCOPY,
};
use windows::Win32::Media::Audio::{
    ActivateAudioInterfaceAsync, IActivateAudioInterfaceAsyncOperation,
    IActivateAudioInterfaceCompletionHandler, IActivateAudioInterfaceCompletionHandler_Vtbl,
    IAudioCaptureClient, IAudioClient, IAudioSessionControl2, IAudioSessionManager2,
    IMMDeviceEnumerator, MMDeviceEnumerator, AUDCLNT_SHAREMODE_SHARED,
    AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM, AUDCLNT_STREAMFLAGS_LOOPBACK,
    AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY, AUDIOCLIENT_ACTIVATION_PARAMS,
    AUDIOCLIENT_ACTIVATION_PARAMS_0, AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
    AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS, AUDCLNT_BUFFERFLAGS_SILENT, eConsole, eRender,
    PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE, VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
    WAVEFORMATEX,
};
use windows::Win32::Storage::Xps::{PrintWindow, PRINT_WINDOW_FLAGS};
use windows::Win32::System::Com::StructuredStorage::{
    PROPVARIANT, PROPVARIANT_0, PROPVARIANT_0_0, PROPVARIANT_0_0_0,
};
use windows::Win32::System::Com::{
    CoCreateInstance, CoInitializeEx, CoTaskMemAlloc, CoUninitialize, BLOB, CLSCTX_ALL,
    COINIT_MULTITHREADED,
};
use windows::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W, TH32CS_SNAPPROCESS,
};
use windows::Win32::System::Variant::VT_BLOB;
use windows::Win32::UI::WindowsAndMessaging::{
    DrawIconEx, EnumWindows, GetClassLongPtrW, GetClassNameW, GetWindowRect, GetWindowTextW,
    GetWindowThreadProcessId, IsIconic, IsWindowVisible, SendMessageTimeoutW, DI_NORMAL,
    GCLP_HICON, GCLP_HICONSM, HICON, ICON_BIG, ICON_SMALL, ICON_SMALL2, SMTO_ABORTIFHUNG,
    WM_GETICON,
};

const FRAME_SAMPLES: usize = 1600;
const PW_RENDERFULLCONTENT: u32 = 2;
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

use super::{encode_rgba_png_data_url, AudioApp};

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

fn exe_stem(exe: &str) -> String {
    exe.strip_suffix(".exe")
        .or_else(|| exe.strip_suffix(".EXE"))
        .unwrap_or(exe)
        .to_string()
}

fn window_label(exe: &str, title: &str) -> String {
    let stem = exe_stem(exe);
    let title = title.trim();
    if title.is_empty() || title.eq_ignore_ascii_case(&stem) || title.eq_ignore_ascii_case(exe) {
        return stem;
    }
    let shown: String = title.chars().take(80).collect();
    format!("{stem} — {shown}")
}

struct ListedWindow {
    pid: u32,
    hwnd: isize,
    title: String,
    visible: bool,
    minimized: bool,
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
    if title.is_empty() || title == "Live Captions" {
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
    let minimized = IsIconic(hwnd).0 != 0;
    ctx.rows.push(ListedWindow {
        pid: root,
        hwnd: hwnd.0 as isize,
        title: title.to_string(),
        visible,
        minimized,
    });
    BOOL(1)
}

unsafe fn create_top_down_dib(hdc: HDC, width: i32, height: i32) -> Option<(windows::Win32::Graphics::Gdi::HBITMAP, *mut u8)> {
    let mut bmi: BITMAPINFO = zeroed();
    bmi.bmiHeader = BITMAPINFOHEADER {
        biSize: size_of::<BITMAPINFOHEADER>() as u32,
        biWidth: width,
        biHeight: -height, // top-down
        biPlanes: 1,
        biBitCount: 32,
        biCompression: BI_RGB.0,
        ..zeroed()
    };
    let mut bits: *mut core::ffi::c_void = null_mut();
    let bmp = CreateDIBSection(Some(hdc), &bmi, DIB_RGB_COLORS, &mut bits, None, 0).ok()?;
    if bits.is_null() {
        let _ = DeleteObject(HGDIOBJ(bmp.0));
        return None;
    }
    Some((bmp, bits.cast::<u8>()))
}

fn bgra_to_rgba(bgra: &[u8], force_opaque: bool) -> Vec<u8> {
    let mut rgba = Vec::with_capacity(bgra.len());
    for chunk in bgra.chunks_exact(4) {
        rgba.push(chunk[2]);
        rgba.push(chunk[1]);
        rgba.push(chunk[0]);
        rgba.push(if force_opaque { 255 } else { chunk[3] });
    }
    rgba
}

fn capture_window_thumbnail(hwnd_raw: isize) -> Option<String> {
    if hwnd_raw == 0 {
        return None;
    }
    let hwnd = HWND(hwnd_raw as *mut core::ffi::c_void);
    unsafe {
        if IsWindowVisible(hwnd).0 == 0 || IsIconic(hwnd).0 != 0 {
            return None;
        }
        let mut rect = RECT::default();
        if GetWindowRect(hwnd, &mut rect).is_err() {
            return None;
        }
        let src_w = rect.right - rect.left;
        let src_h = rect.bottom - rect.top;
        if src_w < 32 || src_h < 32 {
            return None;
        }

        let src_dc = CreateCompatibleDC(None);
        if src_dc.0.is_null() {
            return None;
        }
        let Some((src_bmp, _src_bits)) = create_top_down_dib(src_dc, src_w, src_h) else {
            let _ = DeleteDC(src_dc);
            return None;
        };
        let old_src = SelectObject(src_dc, HGDIOBJ(src_bmp.0));

        let mut captured = PrintWindow(hwnd, src_dc, PRINT_WINDOW_FLAGS(PW_RENDERFULLCONTENT)).0 != 0;
        if !captured {
            captured = PrintWindow(hwnd, src_dc, PRINT_WINDOW_FLAGS(0)).0 != 0;
        }
        if !captured {
            SelectObject(src_dc, old_src);
            let _ = DeleteObject(HGDIOBJ(src_bmp.0));
            let _ = DeleteDC(src_dc);
            return None;
        }

        let max_w = 320.0f64;
        let max_h = 180.0f64;
        let scale = (max_w / src_w as f64).min(max_h / src_h as f64).min(1.0);
        let dst_w = ((src_w as f64 * scale).round() as i32).max(16);
        let dst_h = ((src_h as f64 * scale).round() as i32).max(16);

        let dst_dc = CreateCompatibleDC(Some(src_dc));
        if dst_dc.0.is_null() {
            SelectObject(src_dc, old_src);
            let _ = DeleteObject(HGDIOBJ(src_bmp.0));
            let _ = DeleteDC(src_dc);
            return None;
        }
        let Some((dst_bmp, dst_bits)) = create_top_down_dib(dst_dc, dst_w, dst_h) else {
            let _ = DeleteDC(dst_dc);
            SelectObject(src_dc, old_src);
            let _ = DeleteObject(HGDIOBJ(src_bmp.0));
            let _ = DeleteDC(src_dc);
            return None;
        };
        let old_dst = SelectObject(dst_dc, HGDIOBJ(dst_bmp.0));
        let _ = SetStretchBltMode(dst_dc, HALFTONE);
        let ok = StretchBlt(
            dst_dc,
            0,
            0,
            dst_w,
            dst_h,
            Some(src_dc),
            0,
            0,
            src_w,
            src_h,
            SRCCOPY,
        )
        .0 != 0;

        let rgba = if ok {
            let len = (dst_w as usize) * (dst_h as usize) * 4;
            let slice = std::slice::from_raw_parts(dst_bits, len);
            let non_zero = slice.iter().any(|&b| b != 0);
            if non_zero {
                Some(bgra_to_rgba(slice, true))
            } else {
                None
            }
        } else {
            None
        };

        SelectObject(dst_dc, old_dst);
        let _ = DeleteObject(HGDIOBJ(dst_bmp.0));
        let _ = DeleteDC(dst_dc);
        SelectObject(src_dc, old_src);
        let _ = DeleteObject(HGDIOBJ(src_bmp.0));
        let _ = DeleteDC(src_dc);

        let pixels = rgba?;
        encode_rgba_png_data_url(dst_w as u32, dst_h as u32, &pixels)
    }
}

fn resolve_window_hicon(hwnd: HWND) -> Option<HICON> {
    unsafe {
        for kind in [ICON_SMALL2, ICON_SMALL, ICON_BIG] {
            let mut result = 0usize;
            let _ = SendMessageTimeoutW(
                hwnd,
                WM_GETICON,
                WPARAM(kind as usize),
                LPARAM(0),
                SMTO_ABORTIFHUNG,
                40,
                Some(&mut result),
            );
            if result != 0 {
                return Some(HICON(result as *mut core::ffi::c_void));
            }
        }
        let small = GetClassLongPtrW(hwnd, GCLP_HICONSM);
        if small != 0 {
            return Some(HICON(small as *mut core::ffi::c_void));
        }
        let big = GetClassLongPtrW(hwnd, GCLP_HICON);
        if big != 0 {
            return Some(HICON(big as *mut core::ffi::c_void));
        }
        None
    }
}

fn capture_window_icon(hwnd_raw: isize) -> Option<String> {
    if hwnd_raw == 0 {
        return None;
    }
    let hwnd = HWND(hwnd_raw as *mut core::ffi::c_void);
    let hicon = resolve_window_hicon(hwnd)?;
    unsafe {
        let size = 24i32;
        let dc = CreateCompatibleDC(None);
        if dc.0.is_null() {
            return None;
        }
        let Some((bmp, bits)) = create_top_down_dib(dc, size, size) else {
            let _ = DeleteDC(dc);
            return None;
        };
        let old = SelectObject(dc, HGDIOBJ(bmp.0));
        let len = (size as usize) * (size as usize) * 4;
        ptr::write_bytes(bits, 0, len);
        let drawn = DrawIconEx(dc, 0, 0, hicon, size, size, 0, None, DI_NORMAL).is_ok();
        let rgba = if drawn {
            let slice = std::slice::from_raw_parts(bits, len);
            if slice.iter().any(|&b| b != 0) {
                Some(bgra_to_rgba(slice, false))
            } else {
                None
            }
        } else {
            None
        };
        SelectObject(dc, old);
        let _ = DeleteObject(HGDIOBJ(bmp.0));
        let _ = DeleteDC(dc);
        let pixels = rgba?;
        encode_rgba_png_data_url(size as u32, size as u32, &pixels)
    }
}

fn list_audio_apps_inner() -> Result<Vec<AudioApp>, String> {
    unsafe {
        let coinit = CoInitializeEx(None, COINIT_MULTITHREADED);
        struct CoGuard(bool);
        impl Drop for CoGuard {
            fn drop(&mut self) {
                if self.0 {
                    unsafe { CoUninitialize() };
                }
            }
        }
        let _guard = CoGuard(coinit.is_ok());

        let mut scan = WindowScan {
            tree: process_tree(),
            rows: Vec::new(),
        };
        EnumWindows(Some(enum_top_window), LPARAM(&mut scan as *mut WindowScan as isize))
            .map_err(|e| e.to_string())?;

        // Collect active audio session root PIDs (best-effort)
        let mut audio_pids: HashSet<u32> = HashSet::new();
        if let Ok(enumerator) = CoCreateInstance::<_, IMMDeviceEnumerator>(&MMDeviceEnumerator, None, CLSCTX_ALL) {
            if let Ok(device) = enumerator.GetDefaultAudioEndpoint(eRender, eConsole) {
                if let Ok(manager) = device.Activate::<IAudioSessionManager2>(CLSCTX_ALL, None) {
                    if let Ok(sessions) = manager.GetSessionEnumerator() {
                        if let Ok(count) = sessions.GetCount() {
                            for index in 0..count {
                                let Ok(control) = sessions.GetSession(index) else {
                                    continue;
                                };
                                let Ok(control2) = control.cast::<IAudioSessionControl2>() else {
                                    continue;
                                };
                                // S_OK (0) = system sounds session; S_FALSE (1) = normal app.
                                // Do not use HRESULT::is_ok(): SUCCEEDED(S_FALSE) is true.
                                if control2.IsSystemSoundsSession().0 == 0 {
                                    continue;
                                }
                                let Ok(pid) = control2.GetProcessId() else {
                                    continue;
                                };
                                if pid != 0 {
                                    audio_pids.insert(app_root(pid, &scan.tree));
                                }
                            }
                        }
                    }
                }
            }
        }

        // (label, exe_stem, hwnd, visible, minimized, has_audio)
        let mut found: HashMap<u32, (String, String, isize, bool, bool, bool)> = HashMap::new();
        for row in scan.rows {
            let exe = scan
                .tree
                .get(&row.pid)
                .map(|(_, name)| name.clone())
                .unwrap_or_default();
            let stem = exe_stem(&exe);
            let label = window_label(&exe, &row.title);
            let has_audio = audio_pids.contains(&row.pid);
            let replace = match found.get(&row.pid) {
                None => true,
                Some((_, _, _, prev_vis, prev_min, _)) => {
                    (row.visible && !prev_vis) || (!row.minimized && *prev_min)
                }
            };
            if replace {
                found.insert(
                    row.pid,
                    (label, stem, row.hwnd, row.visible, row.minimized, has_audio),
                );
            }
        }

        for pid in audio_pids {
            if found.contains_key(&pid) {
                continue;
            }
            let exe = scan
                .tree
                .get(&pid)
                .map(|(_, name)| name.clone())
                .filter(|name| !name.is_empty() && !is_shell_exe(name))
                .unwrap_or_else(|| format!("pid {pid}"));
            let stem = exe_stem(&exe);
            found.insert(pid, (stem.clone(), stem, 0, false, false, true));
        }

        let mut apps: Vec<AudioApp> = found
            .into_iter()
            .map(|(pid, (name, stem, hwnd, _, _, has_audio))| {
                let thumbnail = if hwnd != 0 {
                    capture_window_thumbnail(hwnd)
                } else {
                    None
                };
                let icon = if hwnd != 0 {
                    capture_window_icon(hwnd)
                } else {
                    None
                };
                AudioApp {
                    pid,
                    name,
                    app_name: Some(stem),
                    stream_index: None,
                    thumbnail,
                    icon,
                    has_audio,
                }
            })
            .collect();

        apps.sort_by(|a, b| {
            b.has_audio
                .cmp(&a.has_audio)
                .then_with(|| a.name.to_lowercase().cmp(&b.name.to_lowercase()))
        });
        Ok(apps)
    }
}

pub fn list_audio_apps() -> Result<Vec<AudioApp>, String> {
    thread::spawn(list_audio_apps_inner)
        .join()
        .map_err(|_| "Window enumeration worker panicked".to_string())?
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

fn initialize_process_loopback_client(client: &IAudioClient) -> Result<(u32, usize, u16, u16), String> {
    // Process loopback devices (`VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK`) do not
    // implement GetMixFormat() (`E_NOTIMPL`). Specify a concrete PCM format
    // with AUTOCONVERTPCM instead.
    let candidates = [
        WAVEFORMATEX {
            wFormatTag: 1,
            nChannels: 1,
            nSamplesPerSec: 16_000,
            nAvgBytesPerSec: 32_000,
            nBlockAlign: 2,
            wBitsPerSample: 16,
            cbSize: 0,
        },
        WAVEFORMATEX {
            wFormatTag: 1,
            nChannels: 2,
            nSamplesPerSec: 48_000,
            nAvgBytesPerSec: 192_000,
            nBlockAlign: 4,
            wBitsPerSample: 16,
            cbSize: 0,
        },
    ];
    let flags_with_convert = AUDCLNT_STREAMFLAGS_LOOPBACK
        | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM
        | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY;

    let mut last_err = String::from("WASAPI Initialize failed");
    for wfx in candidates {
        for flags in [flags_with_convert, AUDCLNT_STREAMFLAGS_LOOPBACK] {
            let res = unsafe {
                client.Initialize(
                    AUDCLNT_SHAREMODE_SHARED,
                    flags,
                    0,
                    0,
                    &wfx as *const WAVEFORMATEX,
                    None,
                )
            };
            if res.is_ok() {
                return Ok((
                    wfx.nSamplesPerSec,
                    wfx.nChannels as usize,
                    wfx.wBitsPerSample,
                    wfx.nBlockAlign,
                ));
            }
            if let Err(err) = res {
                last_err = err.to_string();
            }
        }
    }
    Err(last_err)
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
        let (rate, channels, bits, block_align) = initialize_process_loopback_client(&client)?;
        let block = block_align as usize;
        let bytes_per_sample = (bits as usize / 8).max(2);

        let capture: IAudioCaptureClient = unsafe { client.GetService().map_err(|e| e.to_string())? };
        unsafe { client.Start().map_err(|e| e.to_string())? };

        let (mut socket, _) = connect(ws_url.as_str()).map_err(|e| e.to_string())?;
        if let tungstenite::stream::MaybeTlsStream::Plain(stream) = socket.get_mut() {
            stream
                .set_read_timeout(Some(Duration::from_millis(40)))
                .map_err(|e| e.to_string())?;
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
                        let offset = frame * block + channel * bytes_per_sample;
                        let sample_i16 = unsafe { *data.add(offset).cast::<i16>() };
                        sum += sample_i16 as f32 / 32768.0;
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
