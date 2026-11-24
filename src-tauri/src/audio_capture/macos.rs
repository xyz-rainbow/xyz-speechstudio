use std::io::Read;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use serde::Deserialize;
use tauri::{AppHandle, Emitter};
use tungstenite::{connect, Message};

use super::{encode_png_bytes_data_url, AudioApp};

const FRAME_BYTES: usize = 3200;

struct Run {
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}

static RUN: Mutex<Option<Run>> = Mutex::new(None);

#[derive(Deserialize)]
struct RawMacWindow {
    pid: u32,
    wid: u32,
    owner: String,
    title: String,
}

fn emit_json(app: &AppHandle, payload: &str) {
    let _ = app.emit("caption", payload);
}

fn capture_window_thumbnail(wid: u32) -> Option<String> {
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_nanos();
    let tmp = std::env::temp_dir().join(format!("speechstudio_win_{wid}_{stamp}.png"));
    let out = Command::new("screencapture")
        .args(["-l", &wid.to_string(), "-x", "-o", "-t", "png"])
        .arg(&tmp)
        .output()
        .ok()?;
    if !out.status.success() || !tmp.is_file() {
        let _ = std::fs::remove_file(&tmp);
        return None;
    }
    let _ = Command::new("sips").args(["-Z", "320"]).arg(&tmp).output();
    let bytes = std::fs::read(&tmp).ok();
    let _ = std::fs::remove_file(&tmp);
    encode_png_bytes_data_url(&bytes?)
}

pub fn list_audio_apps() -> Result<Vec<AudioApp>, String> {
    let script = r#"
ObjC.import('CoreGraphics');
var raw = $.CGWindowListCopyWindowInfo(
  $.kCGWindowListOptionOnScreenOnly | $.kCGWindowListExcludeDesktopElements,
  $.kCGNullWindowID
);
var list = ObjC.deepUnwrap(raw) || [];
var out = [];
for (var i = 0; i < list.length; i++) {
  var w = list[i];
  if ((w.kCGWindowLayer || 0) !== 0) continue;
  var pid = w.kCGWindowOwnerPID || 0;
  var owner = String(w.kCGWindowOwnerName || '').trim();
  var title = String(w.kCGWindowName || '').trim();
  var wid = w.kCGWindowNumber || 0;
  if (!pid || !owner || !wid) continue;
  out.push({ pid: pid, wid: wid, owner: owner, title: title });
}
JSON.stringify(out);
"#;
    let output = Command::new("osascript")
        .args(["-l", "JavaScript", "-e", script])
        .output()
        .map_err(|e| format!("Could not enumerate macOS windows: {e}"))?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }
    let raw_rows: Vec<RawMacWindow> =
        serde_json::from_slice(&output.stdout).unwrap_or_default();

    let mut seen = std::collections::HashSet::new();
    let mut apps = Vec::new();
    for row in raw_rows {
        if !seen.insert(row.pid) {
            continue;
        }
        let label = if row.title.is_empty() || row.title.eq_ignore_ascii_case(&row.owner) {
            row.owner.clone()
        } else {
            format!("{} — {}", row.owner, row.title)
        };
        let thumbnail = capture_window_thumbnail(row.wid);
        apps.push(AudioApp {
            pid: row.pid,
            name: label,
            app_name: Some(row.owner),
            stream_index: None,
            thumbnail,
            icon: None,
            has_audio: false,
        });
    }
    apps.sort_by_key(|a| a.name.to_lowercase());
    Ok(apps)
}

fn find_macos_loopback_input() -> Result<String, String> {
    let out = Command::new("ffmpeg")
        .args(["-f", "avfoundation", "-list_devices", "true", "-i", ""])
        .output()
        .map_err(|e| {
            format!(
                "Live captions on macOS require ffmpeg + a virtual audio loopback device (e.g. BlackHole): {e}"
            )
        })?;
    let stderr = String::from_utf8_lossy(&out.stderr);
    let mut in_audio = false;
    for line in stderr.lines() {
        if line.contains("AVFoundation audio devices") {
            in_audio = true;
            continue;
        }
        if !in_audio {
            continue;
        }
        if let (Some(l), Some(r)) = (line.rfind('['), line.rfind(']')) {
            if r > l + 1 {
                let idx = line[l + 1..r].trim();
                if idx.chars().all(|c| c.is_ascii_digit()) {
                    let low = line.to_lowercase();
                    if low.contains("blackhole") || low.contains("loopback") || low.contains("soundflower") {
                        return Ok(format!(":{idx}"));
                    }
                }
            }
        }
    }
    Err(
        "No virtual audio loopback device found. Install BlackHole (or similar) and set it as the system output; microphone inputs are not used for live captions."
            .into(),
    )
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
    let thread = thread::spawn(move || capture_loop(app, ws_url, language, thread_stop));
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
        }
    }
    Ok(())
}

fn capture_loop(app: AppHandle, ws_url: String, language: String, stop: Arc<AtomicBool>) {
    let result = (|| -> Result<(), String> {
        let input_spec = find_macos_loopback_input()?;
        let mut child = Command::new("ffmpeg")
            .args([
                "-nostdin",
                "-loglevel",
                "error",
                "-f",
                "avfoundation",
                "-i",
                input_spec.as_str(),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "s16le",
                "pipe:1",
            ])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed starting ffmpeg audio capture: {e}"))?;

        let (mut socket, _) = match connect(ws_url.as_str()) {
            Ok(pair) => pair,
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e.to_string());
            }
        };
        if let tungstenite::stream::MaybeTlsStream::Plain(stream) = socket.get_mut() {
            if let Err(e) = stream.set_read_timeout(Some(Duration::from_millis(40))) {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e.to_string());
            }
        }
        let start = format!(
            "{{\"type\":\"start\",\"language\":{}}}",
            serde_json::to_string(&language).unwrap_or_else(|_| "\"auto\"".into())
        );
        if let Err(e) = socket.send(Message::Text(start)) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(e.to_string());
        }

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
                    if err.kind() == std::io::ErrorKind::TimedOut
                        || err.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(_) => break,
                _ => {}
            }
        });

        let mut stdout = child
            .stdout
            .take()
            .ok_or_else(|| "ffmpeg stdout is missing".to_string())?;
        let mut pending = Vec::new();
        let mut buf = [0u8; FRAME_BYTES];
        while !stop.load(Ordering::SeqCst) {
            match stdout.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    pending.extend_from_slice(&buf[..n]);
                    while pending.len() >= FRAME_BYTES {
                        let frame: Vec<u8> = pending.drain(..FRAME_BYTES).collect();
                        let mut sock = socket.lock().unwrap();
                        if sock.send(Message::Binary(frame)).is_err() {
                            stop.store(true, Ordering::SeqCst);
                            break;
                        }
                    }
                }
                Err(err) if err.kind() == std::io::ErrorKind::Interrupted => {}
                Err(err) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(err.to_string());
                }
            }
        }

        {
            let mut sock = socket.lock().unwrap();
            let _ = sock.send(Message::Text("{\"type\":\"stop\"}".into()));
            let _ = sock.close(None);
        }
        stop.store(true, Ordering::SeqCst);
        let _ = reader.join();
        let _ = child.kill();
        let _ = child.wait();
        Ok(())
    })();

    if let Err(err) = result {
        let payload = serde_json::json!({"type": "error", "text": err}).to_string();
        emit_json(&app, &payload);
    }
}
