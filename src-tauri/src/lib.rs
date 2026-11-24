mod audio_capture;
mod notify;
mod selection;
mod sidecar;
mod tray;
mod vram;

use std::process::Command;
use tauri::{Emitter, Manager, RunEvent, State, WindowEvent};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

use sidecar::{BackendInfo, BackendState};
use vram::VramStatus;

#[tauri::command]
fn get_vram_status() -> VramStatus {
    vram::query_vram()
}

#[tauri::command]
fn get_backend_info(state: State<BackendState>) -> BackendInfo {
    state.info()
}

#[tauri::command]
fn toggle_overlay(app: tauri::AppHandle) -> Result<bool, String> {
    if let Some(win) = app.get_webview_window("overlay") {
        let visible = win.is_visible().map_err(|e| e.to_string())?;
        if visible {
            win.hide().map_err(|e| e.to_string())?;
            Ok(false)
        } else {
            win.show().map_err(|e| e.to_string())?;
            let _ = win.set_always_on_top(true);
            Ok(true)
        }
    } else {
        let win = tauri::WebviewWindowBuilder::new(
            &app,
            "overlay",
            tauri::WebviewUrl::App("index.html#/overlay".into()),
        )
        .title("Live Captions")
        .inner_size(620.0, 128.0)
        .decorations(false)
        .transparent(true)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(true)
        .shadow(false)
        .build()
        .map_err(|e| e.to_string())?;
        let _ = win.show();
        Ok(true)
    }
}

#[tauri::command]
fn show_overlay(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("overlay") {
        win.show().map_err(|e| e.to_string())?;
        let _ = win.set_always_on_top(true);
        return Ok(());
    }
    toggle_overlay(app).map(|_| ())
}

#[tauri::command]
fn set_overlay_pinned(app: tauri::AppHandle, pinned: bool) -> Result<(), String> {
    let win = app
        .get_webview_window("overlay")
        .ok_or_else(|| "Overlay window not found".to_string())?;
    win.set_always_on_top(pinned).map_err(|e| e.to_string())
}

#[tauri::command]
fn send_toast(state: State<BackendState>, title: String, message: String, progress: Option<i32>) {
    notify::dispatch_toast(&state.app_root, &title, &message, progress);
}

#[tauri::command]
fn set_read_hotkey(app: tauri::AppHandle, accelerator: String) -> Result<(), String> {
    let gs = app.global_shortcut();
    gs.unregister_all().map_err(|e| e.to_string())?;
    let acc = accelerator.trim();
    if acc.is_empty() {
        return Ok(());
    }
    gs.register(acc).map_err(|e| e.to_string())
}

#[tauri::command]
fn update_tray(app: tauri::AppHandle, labels: tray::TrayLabels) -> Result<(), String> {
    tray::apply_labels(&app, &labels)
}

#[tauri::command]
fn reveal_in_explorer(path: String) -> Result<(), String> {
    let p = std::path::Path::new(&path);
    let mut cmd = Command::new("explorer");
    if p.is_file() {
        cmd.arg(format!("/select,{}", path));
    } else {
        cmd.arg(path);
    }
    cmd.spawn().map_err(|e| e.to_string())?;
    Ok(())
}

#[derive(serde::Deserialize)]
struct HotkeySettings {
    read_hotkey: Option<String>,
}

fn configured_read_hotkey(app_root: &std::path::Path) -> Option<String> {
    let text = std::fs::read_to_string(app_root.join("data").join("settings.json")).ok()?;
    let parsed: HotkeySettings = serde_json::from_str(&text).ok()?;
    parsed.read_hotkey.filter(|s| !s.trim().is_empty())
}

pub fn run() {
    let backend = BackendState::new();
    if let Err(err) = backend.start() {
        eprintln!("[Speech Studio] Backend startup warning: {err}");
    }

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            tray::show_main_window(app);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        let handle = app.clone();
                        std::thread::spawn(move || {
                            let text = selection::read_selected_text();
                            let _ = handle.emit("read-selection", text);
                        });
                    }
                })
                .build(),
        )
        .manage(backend)
        .setup(|app| {
            tray::create_tray(app.handle())?;
            let root = app.state::<BackendState>().app_root.clone();
            if let Some(acc) = configured_read_hotkey(&root) {
                if let Err(e) = app.global_shortcut().register(acc.as_str()) {
                    eprintln!("[Speech Studio] Could not register read hotkey '{acc}': {e}");
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_vram_status,
            get_backend_info,
            toggle_overlay,
            show_overlay,
            set_overlay_pinned,
            audio_capture::list_audio_apps,
            audio_capture::start_live_captions,
            audio_capture::stop_live_captions,
            send_toast,
            reveal_in_explorer,
            set_read_hotkey,
            update_tray,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            audio_capture::stop_live_captions().ok();
            let state = app_handle.state::<BackendState>();
            state.shutdown();
        }
    });
}
