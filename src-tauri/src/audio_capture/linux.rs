use std::collections::HashMap;
use std::io::{ErrorKind, Read};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use tauri::{AppHandle, Emitter};
use tungstenite::{connect, Message};

use super::pactl::{audio_apps_from_inputs, find_sink_input, parse_sink_inputs};
use super::{encode_png_bytes_data_url, AudioApp};

const FRAME_BYTES: usize = 3200;

struct Run {
    stop: Arc<AtomicBool>,
    parec_pid: Arc<AtomicI32>,
    thread: Option<JoinHandle<()>>,
}

static RUN: Mutex<Option<Run>> = Mutex::new(None);

fn emit_json(app: &AppHandle, payload: &str) {
    let _ = app.emit("caption", payload);
}

fn pactl_list() -> Result<String, String> {
    match Command::new("pactl")
        .args(["-f", "json", "list", "sink-inputs"])
        .output()
    {
        Err(err) if err.kind() == ErrorKind::NotFound => {
            Err("pactl was not found. Install pulseaudio-utils (PipeWire or PulseAudio).".into())
        }
        Err(err) => Err(err.to_string()),
        Ok(out) if out.status.success() => Ok(String::from_utf8_lossy(&out.stdout).into_owned()),
        Ok(_) => {
            let plain = Command::new("pactl")
                .args(["list", "sink-inputs"])
                .output()
                .map_err(|err| err.to_string())?;
            if plain.status.success() {
                Ok(String::from_utf8_lossy(&plain.stdout).into_owned())
            } else {
                let err = String::from_utf8_lossy(&plain.stderr);
                let detail = err.trim();
                Err(format!("pactl list sink-inputs failed: {detail}"))
            }
        }
    }
}

fn x11_window_map() -> HashMap<u32, (String, String)> {
    let mut map = HashMap::new();
    let Ok(out) = Command::new("wmctrl").args(["-lp"]).output() else {
        return map;
    };
    if !out.status.success() {
        return map;
    }
    let text = String::from_utf8_lossy(&out.stdout);
    for line in text.lines() {
        let mut parts = line.split_whitespace();
        let Some(wid) = parts.next() else { continue };
        let Some(_desktop) = parts.next() else { continue };
        let Some(pid_str) = parts.next() else { continue };
        let Ok(pid) = pid_str.parse::<u32>() else { continue };
        let Some(_host) = parts.next() else { continue };
        let title: String = parts.collect::<Vec<_>>().join(" ");
        if pid > 0 && !title.trim().is_empty() {
            map.entry(pid)
                .or_insert_with(|| (wid.to_string(), title.trim().to_string()));
        }
    }
    map
}

fn capture_x11_thumbnail(wid: &str) -> Option<String> {
    std::env::var_os("DISPLAY")?;
    let out = Command::new("import")
        .args(["-window", wid, "-resize", "320x180", "png:-"])
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    encode_png_bytes_data_url(&out.stdout)
}

pub fn list_audio_apps() -> Result<Vec<AudioApp>, String> {
    let mut apps = audio_apps_from_inputs(&parse_sink_inputs(&pactl_list()?));
    let x11 = x11_window_map();
    for app in &mut apps {
        if let Some((wid, title)) = x11.get(&app.pid) {
            if let Some(base) = &app.app_name {
                if !title.eq_ignore_ascii_case(base) {
                    app.name = format!("{base} — {title}");
                }
            }
            app.thumbnail = capture_x11_thumbnail(wid);
        }
    }
    Ok(apps)
}

pub fn start_live_captions(
    app: AppHandle,
    pid: u32,
    stream_index: Option<u32>,
    ws_url: String,
    language: String,
) -> Result<(), String> {
    if pid == 0 {
        return Err("Pick an application first".into());
    }
    stop_live_captions()?;
    let stop = Arc::new(AtomicBool::new(false));
    let parec_pid = Arc::new(AtomicI32::new(0));
    let thread_stop = stop.clone();
    let thread_pid = parec_pid.clone();
    let thread = thread::spawn(move || {
        capture_loop(
            app,
            pid,
            stream_index,
            ws_url,
            language,
            thread_stop,
            thread_pid,
        );
    });
    *RUN.lock().unwrap() = Some(Run {
        stop,
        parec_pid,
        thread: Some(thread),
    });
    Ok(())
}

fn signal_parec(pid: i32) {
    if pid > 0 {
        unsafe {
            libc::kill(pid, libc::SIGTERM);
        }
    }
}

pub fn stop_live_captions() -> Result<(), String> {
    let mut run = RUN.lock().unwrap();
    if let Some(mut current) = run.take() {
        current.stop.store(true, Ordering::SeqCst);
        let slot = current.parec_pid.clone();
        signal_parec(slot.load(Ordering::SeqCst));
        let done = Arc::new(AtomicBool::new(false));
        let done_flag = done.clone();
        let killer = thread::spawn(move || {
            while !done_flag.load(Ordering::SeqCst) {
                let pid = slot.load(Ordering::SeqCst);
                if pid > 0 {
                    signal_parec(pid);
                    break;
                }
                thread::sleep(Duration::from_millis(15));
            }
        });
        if let Some(thread) = current.thread.take() {
            drop(run);
            let _ = thread.join();
        }
        done.store(true, Ordering::SeqCst);
        let _ = killer.join();
    }
    Ok(())
}

fn capture_loop(
    app: AppHandle,
    pid: u32,
    stream_index: Option<u32>,
    ws_url: String,
    language: String,
    stop: Arc<AtomicBool>,
    parec_pid: Arc<AtomicI32>,
) {
    let result = (|| -> Result<(), String> {
        if stop.load(Ordering::SeqCst) {
            return Ok(());
        }
        let inputs = parse_sink_inputs(&pactl_list()?);
        let index = find_sink_input(&inputs, pid, stream_index).ok_or_else(|| {
            if stream_index.is_some() {
                "That playback stream is no longer active.".to_string()
            } else {
                "That application has no PulseAudio or PipeWire playback stream.".to_string()
            }
        })?;
        if stop.load(Ordering::SeqCst) {
            return Ok(());
        }
        let index_arg = index.to_string();
        let mut child = Command::new("parec")
            .args([
                "--monitor-stream",
                index_arg.as_str(),
                "--format=s16le",
                "--rate=16000",
                "--channels=1",
                "--latency-msec=40",
            ])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|err| {
                if err.kind() == ErrorKind::NotFound {
                    "parec was not found. Install pulseaudio-utils (PipeWire or PulseAudio).".into()
                } else {
                    err.to_string()
                }
            })?;
        let recorded_pid = i32::try_from(child.id()).unwrap_or(0);
        parec_pid.store(recorded_pid, Ordering::SeqCst);
        if stop.load(Ordering::SeqCst) {
            let _ = child.kill();
            let _ = child.wait();
            parec_pid.store(0, Ordering::SeqCst);
            return Ok(());
        }

        let (mut socket, _) = connect(ws_url.as_str()).map_err(|err| err.to_string())?;
        if let tungstenite::stream::MaybeTlsStream::Plain(stream) = socket.get_mut() {
            stream
                .set_read_timeout(Some(Duration::from_millis(40)))
                .map_err(|err| err.to_string())?;
        }
        let start = format!(
            "{{\"type\":\"start\",\"language\":{}}}",
            serde_json::to_string(&language).unwrap_or_else(|_| "\"auto\"".into())
        );
        socket
            .send(Message::Text(start))
            .map_err(|err| err.to_string())?;
        // UI waits for this before marking the session active.
        emit_json(&app, r#"{"type":"status","text":"started"}"#);
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
                    if err.kind() == ErrorKind::TimedOut || err.kind() == ErrorKind::WouldBlock => {
                }
                Err(_) => break,
                _ => {}
            }
        });

        let mut stdout = child
            .stdout
            .take()
            .ok_or_else(|| "parec stdout is missing".to_string())?;
        let mut pending = Vec::new();
        let mut buf = [0u8; FRAME_BYTES];
        let mut read_error = None;
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
                Err(err) if err.kind() == ErrorKind::Interrupted => {}
                Err(err) => {
                    read_error = Some(err.to_string());
                    break;
                }
            }
        }

        {
            let mut sock = socket.lock().unwrap();
            let _ = sock.send(Message::Text("{\"type\":\"stop\"}".into()));
            let _ = sock.close(None);
        }
        let requested = stop.swap(true, Ordering::SeqCst);
        let _ = reader.join();
        let _ = child.kill();
        let status = child.wait().map_err(|err| err.to_string())?;
        parec_pid.store(0, Ordering::SeqCst);
        if let Some(err) = read_error {
            if !requested {
                return Err(err);
            }
        } else if !status.success() && !requested {
            return Err(format!("parec exited with {status}"));
        }
        Ok(())
    })();

    if let Err(err) = result {
        let payload = serde_json::json!({"type": "error", "text": err}).to_string();
        emit_json(&app, &payload);
    }
}
