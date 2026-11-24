use serde::Serialize;

#[derive(Serialize)]
pub struct AudioApp {
    pub pid: u32,
    pub name: String,
}

mod pactl;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(windows)]
mod windows;

#[cfg(not(any(windows, target_os = "linux")))]
const UNSUPPORTED: &str = "Live captions are not supported on this platform";

#[tauri::command]
pub fn list_audio_apps() -> Result<Vec<AudioApp>, String> {
    #[cfg(windows)]
    return windows::list_audio_apps();
    #[cfg(target_os = "linux")]
    return linux::list_audio_apps();
    #[cfg(not(any(windows, target_os = "linux")))]
    Err(UNSUPPORTED.into())
}

#[tauri::command]
pub fn start_live_captions(
    app: tauri::AppHandle,
    pid: u32,
    ws_url: String,
    language: String,
) -> Result<(), String> {
    #[cfg(windows)]
    return windows::start_live_captions(app, pid, ws_url, language);
    #[cfg(target_os = "linux")]
    return linux::start_live_captions(app, pid, ws_url, language);
    #[cfg(not(any(windows, target_os = "linux")))]
    {
        let _ = (app, pid, ws_url, language);
        Err(UNSUPPORTED.into())
    }
}

#[tauri::command]
pub fn stop_live_captions() -> Result<(), String> {
    #[cfg(windows)]
    return windows::stop_live_captions();
    #[cfg(target_os = "linux")]
    return linux::stop_live_captions();
    #[cfg(not(any(windows, target_os = "linux")))]
    Ok(())
}
