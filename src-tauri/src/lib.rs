mod audio_capture;
mod autostart;
mod dialogs;
mod notify;
mod paths;
mod selection;
mod sidecar;
mod tray;
mod vram;

use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::{Emitter, Manager, RunEvent, State, WindowEvent};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

use sidecar::{BackendInfo, BackendState};
use vram::VramStatus;

static EXITING: AtomicBool = AtomicBool::new(false);

pub fn shutdown_and_exit(app: &tauri::AppHandle) {
    EXITING.store(true, Ordering::SeqCst);
    // Guarantee process exit even if WebView2 or COM teardown stalls.
    std::thread::spawn(|| {
        std::thread::sleep(std::time::Duration::from_millis(1500));
        std::process::exit(0);
    });
    audio_capture::stop_live_captions().ok();
    app.state::<BackendState>().shutdown();
    let _ = app.remove_tray_by_id(tray::TRAY_ID);
    if let Some(win) = app.get_webview_window("overlay") {
        let _ = win.destroy();
    }
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.destroy();
    }
    app.exit(0);
}

#[tauri::command]
fn hide_main_window(app: tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.hide();
    }
}

#[tauri::command]
async fn quit_app(app: tauri::AppHandle) {
    let _ = tauri::async_runtime::spawn_blocking(move || shutdown_and_exit(&app));
}

#[tauri::command]
fn get_vram_status() -> VramStatus {
    vram::query_vram()
}

#[tauri::command]
fn get_backend_info(state: State<BackendState>) -> BackendInfo {
    state.info()
}

#[tauri::command]
async fn toggle_overlay(app: tauri::AppHandle) -> Result<bool, String> {
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
        let width = 620.0;
        let height = 128.0;
        let mut builder = tauri::WebviewWindowBuilder::new(
            &app,
            "overlay",
            tauri::WebviewUrl::App("index.html#/overlay".into()),
        )
        .title("Live Captions")
        .inner_size(width, height)
        .decorations(false)
        .transparent(true)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(true)
        .shadow(false);

        if let Ok(Some(mon)) = app.primary_monitor() {
            let scale = mon.scale_factor();
            let mon_w = mon.size().width as f64 / scale;
            let mon_h = mon.size().height as f64 / scale;
            let mon_x = mon.position().x as f64 / scale;
            let mon_y = mon.position().y as f64 / scale;
            let x = mon_x + ((mon_w - width) / 2.0).max(0.0);
            let y = mon_y + (mon_h - height - 80.0).max(0.0);
            builder = builder.position(x, y);
        } else {
            builder = builder.center();
        }

        let win = builder.build().map_err(|e| e.to_string())?;
        let _ = win.show();
        let _ = win.set_always_on_top(true);
        Ok(true)
    }
}

#[tauri::command]
async fn show_overlay(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("overlay") {
        win.show().map_err(|e| e.to_string())?;
        let _ = win.set_always_on_top(true);
        return Ok(());
    }
    toggle_overlay(app).await.map(|_| ())
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
    #[cfg(windows)]
    {
        let mut cmd = Command::new("explorer");
        if p.is_file() {
            cmd.arg(format!("/select,{}", path));
        } else {
            cmd.arg(path);
        }
        cmd.spawn().map_err(|e| e.to_string())?;
        Ok(())
    }
    #[cfg(target_os = "macos")]
    {
        let mut cmd = Command::new("open");
        if p.is_file() {
            cmd.args(["-R", &path]);
        } else {
            cmd.arg(&path);
        }
        cmd.spawn().map_err(|e| e.to_string())?;
        Ok(())
    }
    #[cfg(target_os = "linux")]
    {
        let reveal = if p.is_file() {
            p.parent()
                .map(|parent| parent.to_path_buf())
                .unwrap_or_else(|| p.to_path_buf())
        } else {
            p.to_path_buf()
        };
        Command::new("xdg-open")
            .arg(reveal)
            .spawn()
            .map_err(|e| e.to_string())?;
        Ok(())
    }
    #[cfg(not(any(windows, target_os = "macos", target_os = "linux")))]
    {
        let _ = p;
        Err("Reveal in file manager is not supported on this platform".to_string())
    }
}

#[cfg(any(windows, target_os = "linux"))]
#[derive(serde::Deserialize)]
struct HotkeySettings {
    read_hotkey: Option<String>,
}

#[cfg(any(windows, target_os = "linux"))]
fn configured_read_hotkey(app_root: &std::path::Path) -> Option<String> {
    let text = std::fs::read_to_string(paths::data_dir(app_root).join("settings.json")).ok()?;
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
                            let payload = selection::read_selection();
                            let _ = handle.emit("read-selection", payload);
                        });
                    }
                })
                .build(),
        )
        .manage(backend)
        .setup(|app| {
            selection::initialize();
            tray::create_tray(app.handle())?;
            if std::env::args().any(|arg| arg == "--minimized") {
                if let Some(win) = app.get_webview_window("main") {
                    let _ = win.hide();
                }
            }
            #[cfg(any(windows, target_os = "linux"))]
            {
                let root = app.state::<BackendState>().app_root.clone();
                if let Some(acc) = configured_read_hotkey(&root) {
                    if let Err(e) = app.global_shortcut().register(acc.as_str()) {
                        eprintln!("[Speech Studio] Could not register read hotkey '{acc}': {e}");
                    }
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    if EXITING.load(Ordering::SeqCst) {
                        return;
                    }
                    api.prevent_close();
                    let _ = window.emit("close-requested", ());
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
            autostart::get_autostart_enabled,
            autostart::set_autostart_enabled,
            dialogs::pick_path,
            hide_main_window,
            quit_app,
            send_toast,
            reveal_in_explorer,
            set_read_hotkey,
            update_tray,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            EXITING.store(true, Ordering::SeqCst);
            audio_capture::stop_live_captions().ok();
            let state = app_handle.state::<BackendState>();
            state.shutdown();
        }
    });
}
