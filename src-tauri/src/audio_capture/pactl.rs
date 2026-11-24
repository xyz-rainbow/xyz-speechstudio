//! PulseAudio / PipeWire sink-input listing.
//!
//! Compiled on every target so the parser tests run on Windows. Linux is the
//! only caller in the app.

#![cfg_attr(not(target_os = "linux"), allow(dead_code))]

use serde_json::Value;

#[derive(Debug, PartialEq, Eq)]
pub struct SinkInput {
    pub index: u32,
    pub pid: u32,
    pub name: String,
}

pub fn parse_sink_inputs(text: &str) -> Vec<SinkInput> {
    let trimmed = text.trim();
    if trimmed.starts_with('[') || trimmed.starts_with('{') {
        if let Ok(value) = serde_json::from_str::<Value>(trimmed) {
            let mut out = Vec::new();
            collect_json(&value, &mut out);
            return out;
        }
    }
    parse_plain(text)
}

pub fn find_sink_input(inputs: &[SinkInput], pid: u32) -> Option<u32> {
    inputs
        .iter()
        .find(|input| input.pid == pid)
        .map(|input| input.index)
}

fn collect_json(value: &Value, out: &mut Vec<SinkInput>) {
    match value {
        Value::Array(items) => {
            for item in items {
                collect_json(item, out);
            }
        }
        Value::Object(map) => {
            if let Some(input) = sink_from_object(map) {
                out.push(input);
            } else {
                for child in map.values() {
                    if child.is_array() || child.is_object() {
                        collect_json(child, out);
                    }
                }
            }
        }
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {}
    }
}

fn sink_from_object(map: &serde_json::Map<String, Value>) -> Option<SinkInput> {
    let index = json_u32(map.get("index"))?;
    let props = map.get("properties")?.as_object()?;
    let pid = json_u32(props.get("application.process.id"))?;
    let name = json_string(props.get("application.name"))
        .or_else(|| json_string(props.get("application.process.binary")))
        .or_else(|| json_string(props.get("media.name")))
        .unwrap_or_else(|| format!("pid {pid}"));
    Some(SinkInput { index, pid, name })
}

fn json_u32(value: Option<&Value>) -> Option<u32> {
    match value? {
        Value::Number(number) => number.as_u64().and_then(|n| u32::try_from(n).ok()),
        Value::String(text) => text.trim().parse().ok(),
        _ => None,
    }
}

fn json_string(value: Option<&Value>) -> Option<String> {
    let text = value?.as_str()?.trim();
    if text.is_empty() {
        None
    } else {
        Some(text.to_string())
    }
}

fn parse_plain(text: &str) -> Vec<SinkInput> {
    let mut out = Vec::new();
    let mut index = None;
    let mut pid = None;
    let mut name = None;
    for raw in text.lines() {
        let line = raw.trim();
        if let Some(rest) = line.strip_prefix("Sink Input #") {
            push_plain(&mut out, index, pid, &mut name);
            index = rest.split_whitespace().next().and_then(|s| s.parse().ok());
            pid = None;
            name = None;
            continue;
        }
        if let Some(value) = prop_value(line, "application.process.id") {
            pid = unquote(value).parse().ok();
        } else if let Some(value) = prop_value(line, "application.name") {
            name = Some(unquote(value));
        } else if name.is_none() {
            name = prop_value(line, "application.process.binary").map(unquote);
        }
    }
    push_plain(&mut out, index, pid, &mut name);
    out
}

fn push_plain(
    out: &mut Vec<SinkInput>,
    index: Option<u32>,
    pid: Option<u32>,
    name: &mut Option<String>,
) {
    if let (Some(index), Some(pid)) = (index, pid) {
        out.push(SinkInput {
            index,
            pid,
            name: name.take().unwrap_or_else(|| format!("pid {pid}")),
        });
    }
}

fn prop_value<'a>(line: &'a str, key: &str) -> Option<&'a str> {
    let rest = line.strip_prefix(key)?.trim_start();
    let rest = rest.strip_prefix('=')?.trim();
    if rest.is_empty() {
        None
    } else {
        Some(rest)
    }
}

fn unquote(value: &str) -> String {
    value.trim().trim_matches('"').trim().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_pactl_json_array() {
        let text = r#"[
          {
            "index": 67,
            "properties": {
              "application.name": "Firefox",
              "application.process.id": "4242",
              "application.process.binary": "firefox"
            }
          },
          {
            "index": 68,
            "properties": {
              "media.name": "silence"
            }
          }
        ]"#;
        let parsed = parse_sink_inputs(text);
        assert_eq!(
            parsed,
            vec![SinkInput {
                index: 67,
                pid: 4242,
                name: "Firefox".into(),
            }]
        );
        assert_eq!(find_sink_input(&parsed, 4242), Some(67));
    }

    #[test]
    fn parses_pactl_json_object_and_numeric_pid() {
        let text = r#"{
          "80": {
            "index": 80,
            "properties": {
              "application.process.id": 99,
              "application.process.binary": "discord"
            }
          }
        }"#;
        assert_eq!(
            parse_sink_inputs(text),
            vec![SinkInput {
                index: 80,
                pid: 99,
                name: "discord".into(),
            }]
        );
    }

    #[test]
    fn parses_plain_pactl_text() {
        let text = r#"
Sink Input #184
	Driver: PipeWire
	Properties:
		application.name = "Firefox"
		application.process.id = "4242"
		application.process.binary = "firefox"

Sink Input #185
	Properties:
		application.process.id = "7"
		application.process.binary = "mpv"
"#;
        assert_eq!(
            parse_sink_inputs(text),
            vec![
                SinkInput {
                    index: 184,
                    pid: 4242,
                    name: "Firefox".into(),
                },
                SinkInput {
                    index: 185,
                    pid: 7,
                    name: "mpv".into(),
                },
            ]
        );
    }

    #[test]
    fn empty_text_has_no_inputs() {
        assert!(parse_sink_inputs("").is_empty());
        assert!(parse_sink_inputs("Sink Input #3\n").is_empty());
    }
}
