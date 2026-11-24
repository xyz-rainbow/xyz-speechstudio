use serde::Serialize;

#[derive(Serialize)]
pub struct AudioApp {
    pub pid: u32,
    pub name: String,
}

#[cfg(windows)]
mod windows;

#[cfg(windows)]
pub use windows::{list_audio_apps, start_live_captions, stop_live_captions};

const UNSUPPORTED: &str = "Live captions are not supported on this platform";

#[cfg(not(windows))]
#[tauri::command]
pub fn list_audio_apps() -> Result<Vec<AudioApp>, String> {
    Err(UNSUPPORTED.into())
}

#[cfg(not(windows))]
#[tauri::command]
pub fn start_live_captions(
    _app: tauri::AppHandle,
    _pid: u32,
    _ws_url: String,
    _language: String,
) -> Result<(), String> {
    Err(UNSUPPORTED.into())
}

#[cfg(not(windows))]
#[tauri::command]
pub fn stop_live_captions() -> Result<(), String> {
    Ok(())
}