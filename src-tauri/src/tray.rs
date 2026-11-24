use serde::{Deserialize, Serialize};
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager};

pub const TRAY_ID: &str = "main-tray";

#[derive(Deserialize, Serialize, Clone)]
pub struct TrayLabels {
    pub open: String,
    pub show_hide: String,
    pub subtitles: String,
    pub stop_subtitles: String,
    pub eject: String,
    pub exit: String,
    pub subtitles_active: bool,
}

impl Default for TrayLabels {
    fn default() -> Self {
        Self {
            open: "Open Speech Studio".into(),
            show_hide: "Show / Hide".into(),
            subtitles: "Live Captions".into(),
            stop_subtitles: "Stop Live Captions".into(),
            eject: "Eject models (TTS + STT)".into(),
            exit: "Exit".into(),
            subtitles_active: false,
        }
    }
}

pub fn show_main_window(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.unminimize();
        let _ = win.set_focus();
    }
}

fn toggle_main_window(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let visible = win.is_visible().unwrap_or(false);
        let minimized = win.is_minimized().unwrap_or(false);
        if visible && !minimized {
            let _ = win.hide();
        } else {
            show_main_window(app);
        }
    }
}

fn build_menu(app: &AppHandle, labels: &TrayLabels) -> tauri::Result<Menu<tauri::Wry>> {
    let open = MenuItem::with_id(app, "open", &labels.open, true, None::<&str>)?;
    let show_hide = MenuItem::with_id(app, "show_hide", &labels.show_hide, true, None::<&str>)?;
    let subtitles = MenuItem::with_id(app, "subtitles", &labels.subtitles, true, None::<&str>)?;
    let eject = MenuItem::with_id(app, "eject", &labels.eject, true, None::<&str>)?;
    let exit = MenuItem::with_id(app, "exit", &labels.exit, true, None::<&str>)?;
    let sep1 = PredefinedMenuItem::separator(app)?;
    let sep2 = PredefinedMenuItem::separator(app)?;

    if labels.subtitles_active {
        let stop = MenuItem::with_id(app, "stop_subtitles", &labels.stop_subtitles, true, None::<&str>)?;
        Menu::with_items(
            app,
            &[&open, &show_hide, &sep1, &subtitles, &stop, &sep2, &eject, &exit],
        )
    } else {
        Menu::with_items(app, &[&open, &show_hide, &sep1, &subtitles, &sep2, &eject, &exit])
    }
}

pub fn create_tray(app: &AppHandle) -> tauri::Result<()> {
    let labels = TrayLabels::default();
    let menu = build_menu(app, &labels)?;

    // Linux and macOS open the menu with the primary click. Windows uses that
    // click only to show the window. Linux also shows the window on that click,
    // so the app can be reopened when a desktop does not deliver a separate
    // activate event. Ubuntu and macOS have not been tried from this tree.
    let menu_on_left_click = cfg!(any(target_os = "linux", target_os = "macos"));
    let mut builder = TrayIconBuilder::with_id(TRAY_ID)
        .tooltip("Speech Studio")
        .menu(&menu)
        .show_menu_on_left_click(menu_on_left_click)
        .icon_as_template(cfg!(target_os = "macos"))
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => show_main_window(app),
            "show_hide" => toggle_main_window(app),
            "subtitles" => {
                show_main_window(app);
                let _ = app.emit("tray-action", "subtitles");
            }
            "stop_subtitles" => {
                let _ = app.emit("tray-action", "stop_subtitles");
            }
            "eject" => {
                let _ = app.emit("tray-action", "eject");
            }
            "exit" => {
                crate::shutdown_and_exit(app);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                // Windows and Linux show the window. Linux still opens the menu
                // because show_menu_on_left_click stays on. macOS keeps the
                // click for the menu. The Open item calls show_main_window too.
                #[cfg(any(windows, target_os = "linux"))]
                show_main_window(tray.app_handle());
                #[cfg(not(any(windows, target_os = "linux")))]
                let _ = tray;
            }
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    builder.build(app)?;
    Ok(())
}

pub fn apply_labels(app: &AppHandle, labels: &TrayLabels) -> Result<(), String> {
    let menu = build_menu(app, labels).map_err(|e| e.to_string())?;
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        tray.set_menu(Some(menu)).map_err(|e| e.to_string())?;
    }
    Ok(())
}
