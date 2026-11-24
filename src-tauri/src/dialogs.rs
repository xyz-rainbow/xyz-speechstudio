use serde::Deserialize;

#[derive(Deserialize)]
pub struct DialogFilter {
    pub name: String,
    pub extensions: Vec<String>,
}

#[tauri::command]
pub async fn pick_path(
    #[cfg_attr(not(target_os = "macos"), allow(unused_variables))] app: tauri::AppHandle,
    directory: bool,
    title: Option<String>,
    filters: Vec<DialogFilter>,
) -> Result<Option<String>, String> {
    #[cfg(target_os = "macos")]
    {
        let (tx, rx) = std::sync::mpsc::sync_channel::<Option<String>>(1);
        app.run_on_main_thread(move || {
            let mut dlg = rfd::AsyncFileDialog::new();
            if let Some(t) = title {
                dlg = dlg.set_title(t);
            }
            for f in &filters {
                let exts: Vec<&str> = f.extensions.iter().map(String::as_str).collect();
                dlg = dlg.add_filter(&f.name, &exts);
            }
            let fut = async move {
                let picked = if directory {
                    dlg.pick_folder().await
                } else {
                    dlg.pick_file().await
                };
                picked.map(|h| h.path().to_string_lossy().into_owned())
            };
            std::thread::spawn(move || {
                let _ = tx.send(tauri::async_runtime::block_on(fut));
            });
        })
        .map_err(|e| e.to_string())?;
        tauri::async_runtime::spawn_blocking(move || rx.recv().unwrap_or(None))
            .await
            .map_err(|e| e.to_string())
    }

    #[cfg(windows)]
    {
        tauri::async_runtime::spawn_blocking(move || {
            let mut dlg = rfd::FileDialog::new();
            if let Some(t) = title {
                dlg = dlg.set_title(t);
            }
            for f in &filters {
                let exts: Vec<&str> = f.extensions.iter().map(String::as_str).collect();
                dlg = dlg.add_filter(&f.name, &exts);
            }
            let picked = if directory {
                dlg.pick_folder()
            } else {
                dlg.pick_file()
            };
            picked.map(|p| p.to_string_lossy().into_owned())
        })
        .await
        .map_err(|e| e.to_string())
    }

    #[cfg(not(any(windows, target_os = "macos")))]
    {
        let mut dlg = rfd::AsyncFileDialog::new();
        if let Some(t) = title {
            dlg = dlg.set_title(t);
        }
        for f in &filters {
            let exts: Vec<&str> = f.extensions.iter().map(String::as_str).collect();
            dlg = dlg.add_filter(&f.name, &exts);
        }
        let picked = if directory {
            dlg.pick_folder().await
        } else {
            dlg.pick_file().await
        };
        Ok(picked.map(|h| h.path().to_string_lossy().into_owned()))
    }
}
