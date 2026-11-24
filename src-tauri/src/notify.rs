use std::path::Path;
#[cfg(any(windows, target_os = "linux"))]
use std::path::PathBuf;

#[cfg(any(windows, target_os = "macos"))]
const APP_ID: &str = "com.xyz.speechstudio";
#[cfg(any(windows, target_os = "linux"))]
const APP_NAME: &str = "Speech Studio";

/// Desktop toast branded as Speech Studio.
///
/// Windows uses the app id plus a Start Menu shortcut of the same name.
/// Linux uses `notify-send -a`. macOS sends the notification from this process.
pub fn dispatch_toast(app_root: &Path, title: &str, message: &str, progress: Option<i32>) {
    #[cfg(windows)]
    dispatch_windows(app_root, title, message, progress);
    #[cfg(target_os = "macos")]
    dispatch_macos(app_root, title, message, progress);
    #[cfg(target_os = "linux")]
    dispatch_linux(app_root, title, message, progress);
    #[cfg(not(any(windows, target_os = "macos", target_os = "linux")))]
    {
        let _ = (app_root, title, message, progress);
    }
}

fn with_progress(message: &str, progress: Option<i32>) -> String {
    match progress {
        Some(pct) => format!("{message} ({}%)", pct.clamp(0, 100)),
        None => message.to_string(),
    }
}

#[cfg(any(windows, target_os = "linux"))]
fn find_icon(app_root: &Path) -> Option<PathBuf> {
    let mut candidates = vec![
        app_root.join("src-tauri").join("icons").join("128x128.png"),
        app_root.join("icons").join("128x128.png"),
        app_root.join("src-tauri").join("icons").join("icon.png"),
    ];
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("icons").join("128x128.png"));
            candidates.push(dir.join("128x128.png"));
        }
    }
    candidates.into_iter().find(|path| path.is_file())
}

#[cfg(windows)]
fn find_ico(app_root: &Path) -> Option<PathBuf> {
    let mut candidates = vec![
        app_root.join("src-tauri").join("icons").join("icon.ico"),
        app_root.join("icons").join("icon.ico"),
    ];
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("icons").join("icon.ico"));
            candidates.push(dir.join("icon.ico"));
        }
    }
    candidates.into_iter().find(|path| path.is_file())
}

#[cfg(windows)]
fn dispatch_windows(app_root: &Path, title: &str, message: &str, progress: Option<i32>) {
    use winrt_notification::{IconCrop, Toast};

    ensure_app_shortcut(app_root);
    let body = with_progress(message, progress);
    let built = Toast::new(APP_ID).title(title).text1(&body);
    let shown = match find_icon(app_root) {
        Some(icon) => built.icon(&icon, IconCrop::Square, APP_NAME).show(),
        None => built.show(),
    };
    let _ = shown;
}

#[cfg(windows)]
fn ensure_app_shortcut(app_root: &Path) {
    use std::sync::atomic::{AtomicBool, Ordering};

    static READY: AtomicBool = AtomicBool::new(false);
    if READY.load(Ordering::Acquire) {
        return;
    }
    if register_start_menu_shortcut(app_root).is_ok() {
        READY.store(true, Ordering::Release);
    }
}

#[cfg(windows)]
fn register_start_menu_shortcut(app_root: &Path) -> std::io::Result<()> {
    use std::env;
    use windows::core::{Interface, GUID, PCWSTR};
    use windows::Win32::Foundation::PROPERTYKEY;
    use windows::Win32::System::Com::{
        CoCreateInstance, CoInitializeEx, CoUninitialize, IPersistFile, CLSCTX_INPROC_SERVER,
        COINIT_APARTMENTTHREADED,
    };
    use windows::Win32::UI::Shell::PropertiesSystem::IPropertyStore;
    use windows::Win32::UI::Shell::{IShellLinkW, ShellLink};

    const PKEY_APP_USER_MODEL_ID: PROPERTYKEY = PROPERTYKEY {
        fmtid: GUID::from_u128(0x9f4c2855_9f79_4b39_a8d0_e1d42de1d5f3),
        pid: 5,
    };

    let exe = env::current_exe()?;
    let workdir = exe
        .parent()
        .map(Path::to_path_buf)
        .ok_or_else(|| std::io::Error::other("executable has no parent directory"))?;
    let appdata = env::var_os("APPDATA").ok_or_else(|| {
        std::io::Error::new(std::io::ErrorKind::NotFound, "APPDATA is not set")
    })?;
    let shortcut = PathBuf::from(appdata)
        .join("Microsoft")
        .join("Windows")
        .join("Start Menu")
        .join("Programs")
        .join("Speech Studio.lnk");
    if let Some(dir) = shortcut.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let icon = find_ico(app_root).unwrap_or_else(|| exe.clone());

    let exe_w = wide_os(exe.as_os_str());
    let work_w = wide_os(workdir.as_os_str());
    let icon_w = wide_os(icon.as_os_str());
    let desc_w = wide(APP_NAME);
    let app_w = wide(APP_ID);
    let link_w = wide_os(shortcut.as_os_str());

    unsafe {
        let init = CoInitializeEx(None, COINIT_APARTMENTTHREADED);
        let owned = init.is_ok();
        let result = (|| -> windows::core::Result<()> {
            let shell: IShellLinkW = CoCreateInstance(&ShellLink, None, CLSCTX_INPROC_SERVER)?;
            shell.SetPath(PCWSTR(exe_w.as_ptr()))?;
            shell.SetWorkingDirectory(PCWSTR(work_w.as_ptr()))?;
            shell.SetIconLocation(PCWSTR(icon_w.as_ptr()), 0)?;
            shell.SetDescription(PCWSTR(desc_w.as_ptr()))?;
            let store: IPropertyStore = shell.cast()?;
            let variant = string_propvariant(&app_w)?;
            store.SetValue(&PKEY_APP_USER_MODEL_ID, &variant)?;
            store.Commit()?;
            let file: IPersistFile = shell.cast()?;
            file.Save(PCWSTR(link_w.as_ptr()), true)?;
            Ok(())
        })();
        if owned {
            CoUninitialize();
        }
        result.map_err(|err| std::io::Error::other(err.to_string()))
    }
}

#[cfg(windows)]
fn wide(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(std::iter::once(0)).collect()
}

#[cfg(windows)]
fn wide_os(value: &std::ffi::OsStr) -> Vec<u16> {
    use std::os::windows::ffi::OsStrExt;
    value.encode_wide().chain(std::iter::once(0)).collect()
}

#[cfg(windows)]
unsafe fn string_propvariant(
    utf16_nul: &[u16],
) -> windows::core::Result<windows::Win32::System::Com::StructuredStorage::PROPVARIANT> {
    use std::mem::ManuallyDrop;
    use windows::core::{Error, PWSTR};
    use windows::Win32::Foundation::E_OUTOFMEMORY;
    use windows::Win32::System::Com::CoTaskMemAlloc;
    use windows::Win32::System::Com::StructuredStorage::{
        PROPVARIANT, PROPVARIANT_0, PROPVARIANT_0_0, PROPVARIANT_0_0_0,
    };
    use windows::Win32::System::Variant::VT_LPWSTR;

    // PropVariantClear() frees VT_LPWSTR via CoTaskMemFree; allocate on the COM heap.
    let byte_len = utf16_nul.len() * std::mem::size_of::<u16>();
    let buf = CoTaskMemAlloc(byte_len) as *mut u16;
    if buf.is_null() {
        return Err(Error::from(E_OUTOFMEMORY));
    }
    std::ptr::copy_nonoverlapping(utf16_nul.as_ptr(), buf, utf16_nul.len());

    Ok(PROPVARIANT {
        Anonymous: PROPVARIANT_0 {
            Anonymous: ManuallyDrop::new(PROPVARIANT_0_0 {
                vt: VT_LPWSTR,
                wReserved1: 0,
                wReserved2: 0,
                wReserved3: 0,
                Anonymous: PROPVARIANT_0_0_0 { pwszVal: PWSTR(buf) },
            }),
        },
    })
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;

    #[test]
    fn propvariant_drop_does_not_corrupt_heap() {
        let w = wide(APP_ID);
        unsafe {
            let v = string_propvariant(&w).expect("CoTaskMemAlloc");
            drop(v);
        }
    }
}

#[cfg(target_os = "linux")]
fn dispatch_linux(app_root: &Path, title: &str, message: &str, progress: Option<i32>) {
    use std::process::Command;
    let text = with_progress(message, progress);
    let mut cmd = Command::new("notify-send");
    cmd.args(["-a", APP_NAME]);
    if let Some(icon) = find_icon(app_root) {
        cmd.arg("-i").arg(icon);
    }
    cmd.arg(title).arg(text);
    let _ = cmd.spawn();
}

#[cfg(target_os = "macos")]
fn dispatch_macos(_app_root: &Path, title: &str, message: &str, progress: Option<i32>) {
    use mac_notification_sys::{send_notification, set_application};
    use std::sync::Once;

    static INIT: Once = Once::new();
    INIT.call_once(|| {
        let _ = set_application(APP_ID);
    });
    let text = with_progress(message, progress);
    let _ = send_notification(title, None, &text, None);
}
