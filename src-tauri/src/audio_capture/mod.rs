use base64::Engine as _;
use serde::Serialize;

#[derive(Serialize, Clone, Debug)]
pub struct AudioApp {
    pub pid: u32,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub app_name: Option<String>,
    /// Sink-input index on Linux. Absent on Windows/macOS.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stream_index: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub thumbnail: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub icon: Option<String>,
    #[serde(default)]
    pub has_audio: bool,
}

#[cfg(any(windows, test))]
pub(crate) fn encode_rgba_png_data_url(width: u32, height: u32, rgba: &[u8]) -> Option<String> {
    if width == 0 || height == 0 {
        return None;
    }
    let expected = (width as usize).checked_mul(height as usize)?.checked_mul(4)?;
    if rgba.len() != expected {
        return None;
    }
    let mut png_bytes = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut png_bytes, width, height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().ok()?;
        writer.write_image_data(rgba).ok()?;
    }
    let encoded = base64::engine::general_purpose::STANDARD.encode(&png_bytes);
    Some(format!("data:image/png;base64,{encoded}"))
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
pub(crate) fn encode_png_bytes_data_url(png_bytes: &[u8]) -> Option<String> {
    if png_bytes.is_empty() {
        return None;
    }
    let encoded = base64::engine::general_purpose::STANDARD.encode(png_bytes);
    Some(format!("data:image/png;base64,{encoded}"))
}

mod pactl;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "macos")]
mod macos;
#[cfg(windows)]
mod windows;

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
const UNSUPPORTED: &str = "Live captions are not supported on this platform";

#[tauri::command]
pub async fn list_audio_apps() -> Result<Vec<AudioApp>, String> {
    tauri::async_runtime::spawn_blocking(|| {
        #[cfg(windows)]
        return windows::list_audio_apps();
        #[cfg(target_os = "linux")]
        return linux::list_audio_apps();
        #[cfg(target_os = "macos")]
        return macos::list_audio_apps();
        #[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
        Err(UNSUPPORTED.into())
    })
    .await
    .map_err(|e| format!("Window scan task failed: {e}"))?
}

#[tauri::command]
pub fn start_live_captions(
    app: tauri::AppHandle,
    pid: u32,
    stream_index: Option<u32>,
    ws_url: String,
    language: String,
) -> Result<(), String> {
    #[cfg(windows)]
    {
        let _ = stream_index;
        windows::start_live_captions(app, pid, ws_url, language)
    }
    #[cfg(target_os = "linux")]
    {
        linux::start_live_captions(app, pid, stream_index, ws_url, language)
    }
    #[cfg(target_os = "macos")]
    {
        let _ = stream_index;
        macos::start_live_captions(app, pid, ws_url, language)
    }
    #[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
    {
        let _ = (app, pid, stream_index, ws_url, language);
        Err(UNSUPPORTED.into())
    }
}

#[tauri::command]
pub fn stop_live_captions() -> Result<(), String> {
    #[cfg(windows)]
    return windows::stop_live_captions();
    #[cfg(target_os = "linux")]
    return linux::stop_live_captions();
    #[cfg(target_os = "macos")]
    return macos::stop_live_captions();
    #[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn encodes_valid_rgba_png_data_url() {
        let rgba = [255u8, 0, 128, 255, 0, 255, 64, 255];
        let uri = encode_rgba_png_data_url(2, 1, &rgba).expect("expected PNG data URL");
        assert!(uri.starts_with("data:image/png;base64,"));
        let raw = base64::engine::general_purpose::STANDARD
            .decode(uri.trim_start_matches("data:image/png;base64,"))
            .expect("valid base64");
        assert_eq!(&raw[..8], b"\x89PNG\r\n\x1a\n");
    }

    #[test]
    fn rejects_invalid_rgba_dimensions() {
        assert!(encode_rgba_png_data_url(0, 10, &[]).is_none());
        assert!(encode_rgba_png_data_url(2, 2, &[0u8; 8]).is_none());
    }
}
