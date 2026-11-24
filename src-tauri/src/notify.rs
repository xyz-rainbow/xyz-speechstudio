use std::path::Path;
use std::process::Command;

/// Shows a desktop toast. Windows uses BurntToast. Linux (`notify-send`) and
/// macOS (`osascript`) are implemented and still pending a real build.
pub fn dispatch_toast(app_root: &Path, title: &str, message: &str, progress: Option<i32>) {
    #[cfg(windows)]
    dispatch_windows(app_root, title, message, progress);
    #[cfg(target_os = "macos")]
    {
        let _ = app_root;
        dispatch_macos(title, message, progress);
    }
    #[cfg(target_os = "linux")]
    {
        let _ = app_root;
        dispatch_linux(title, message, progress);
    }
    #[cfg(not(any(windows, target_os = "macos", target_os = "linux")))]
    {
        let _ = (app_root, title, message, progress);
    }
}

#[cfg(windows)]
fn dispatch_windows(app_root: &Path, title: &str, message: &str, progress: Option<i32>) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;

    let script = app_root.join("scripts").join("notify.ps1");
    if !script.exists() {
        return;
    }
    let mut args = vec![
        "-NoProfile".to_string(),
        "-ExecutionPolicy".into(),
        "Bypass".into(),
        "-File".into(),
        script.to_string_lossy().into_owned(),
        "-Title".into(),
        title.to_string(),
        "-Message".into(),
        message.to_string(),
    ];
    if let Some(pct) = progress {
        args.push("-Progress".into());
        args.push(pct.clamp(0, 100).to_string());
    }
    let arg_refs: Vec<&str> = args.iter().map(String::as_str).collect();
    let spawned = Command::new("pwsh")
        .creation_flags(CREATE_NO_WINDOW)
        .args(&arg_refs)
        .spawn();
    if spawned.is_err() {
        let _ = Command::new("powershell")
            .creation_flags(CREATE_NO_WINDOW)
            .args(&arg_refs)
            .spawn();
    }
}

#[cfg(target_os = "macos")]
fn dispatch_macos(title: &str, message: &str, progress: Option<i32>) {
    let text = with_progress(message, progress);
    let script = format!(
        "display notification {} with title {}",
        apple_string(&text),
        apple_string(title)
    );
    let _ = Command::new("osascript").args(["-e", &script]).spawn();
}

#[cfg(target_os = "linux")]
fn dispatch_linux(title: &str, message: &str, progress: Option<i32>) {
    let text = with_progress(message, progress);
    let _ = Command::new("notify-send").args([title, &text]).spawn();
}

#[cfg(any(target_os = "macos", target_os = "linux"))]
fn with_progress(message: &str, progress: Option<i32>) -> String {
    match progress {
        Some(pct) => format!("{message} ({}%)", pct.clamp(0, 100)),
        None => message.to_string(),
    }
}

#[cfg(target_os = "macos")]
fn apple_string(value: &str) -> String {
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}
