use serde::Serialize;

#[derive(Serialize)]
pub struct AudioApp {
    pub pid: u32,
    pub name: String,
}

#[cfg(windows)]
mod windows;

const UNSUPPORTED: &str = "Live captions are not supported on this platform";

#[tauri::command]
pub fn list_audio_apps() -> Result<Vec<AudioApp>, String> {
    #[cfg(windows)]
    return windows::list_audio_apps();
    #[cfg(not(windows))]
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
    #[cfg(not(windows))]
    {
        let _ = (app, pid, ws_url, language);
        Err(UNSUPPORTED.into())
    }
}

#[tauri::command]
pub fn stop_live_captions() -> Result<(), String> {
    #[cfg(windows)]
    return windows::stop_live_captions();
    #[cfg(not(windows))]
    Ok(())
}