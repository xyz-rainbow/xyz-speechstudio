use std::os::windows::process::CommandExt;
use std::path::Path;
use std::process::Command;

const CREATE_NO_WINDOW: u32 = 0x0800_0000;

pub fn dispatch_toast(app_root: &Path, title: &str, message: &str, progress: Option<i32>) {
    let script = app_root.join("scripts").join("notify.ps1");
    if !script.exists() {
        return;
    }
    let mut cmd = Command::new("powershell");
    cmd.creation_flags(CREATE_NO_WINDOW)
        .args([
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            &script.to_string_lossy(),
            "-Title",
            title,
            "-Message",
            message,
        ]);
    if let Some(pct) = progress {
        cmd.args(["-Progress", &pct.clamp(0, 100).to_string()]);
    }
    let _ = cmd.spawn();
}
