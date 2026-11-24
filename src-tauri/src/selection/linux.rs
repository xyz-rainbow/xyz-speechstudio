use std::io::Read;
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use super::SelectionPayload;

const TIMEOUT: Duration = Duration::from_millis(800);

enum ToolOut {
    Missing,
    Text(String),
    None,
}

/// Primary selection only. Never `wl-paste` without `--primary`, and never
/// `xclip -selection clipboard`.
pub fn read_primary_selection() -> SelectionPayload {
    let wayland = run_tool("wl-paste", &["--primary", "--no-newline"]);
    if let ToolOut::Text(text) = wayland {
        return SelectionPayload::text(text);
    }
    let x11 = run_tool("xclip", &["-o", "-selection", "primary"]);
    if let ToolOut::Text(text) = x11 {
        return SelectionPayload::text(text);
    }
    if matches!(wayland, ToolOut::Missing) && matches!(x11, ToolOut::Missing) {
        return SelectionPayload::unavailable();
    }
    SelectionPayload::empty()
}

fn run_tool(program: &str, args: &[&str]) -> ToolOut {
    let mut child = match Command::new(program)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => child,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return ToolOut::Missing,
        Err(_) => return ToolOut::None,
    };

    let started = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                let mut raw = Vec::new();
                if let Some(mut stdout) = child.stdout.take() {
                    let _ = stdout.read_to_end(&mut raw);
                }
                if !status.success() {
                    return ToolOut::None;
                }
                let text = String::from_utf8_lossy(&raw).trim().to_string();
                if text.is_empty() {
                    return ToolOut::None;
                }
                return ToolOut::Text(text);
            }
            Ok(None) if started.elapsed() >= TIMEOUT => {
                let _ = child.kill();
                let _ = child.wait();
                return ToolOut::None;
            }
            Ok(None) => thread::sleep(Duration::from_millis(20)),
            Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                return ToolOut::None;
            }
        }
    }
}
