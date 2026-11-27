use std::path::{Path, PathBuf};

pub fn data_dir(app_root: &Path) -> PathBuf {
    resolve_data_dir(app_root, std::env::consts::OS, |key| std::env::var(key).ok())
}

fn resolve_data_dir(
    app_root: &Path,
    platform: &str,
    env: impl Fn(&str) -> Option<String>,
) -> PathBuf {
    if let Some(value) = env("SPEECHSTUDIO_DATA_DIR").filter(|s| !s.trim().is_empty()) {
        let path = PathBuf::from(value.trim());
        return if path.is_absolute() { path } else { app_root.join(path) };
    }
    let legacy = app_root.join("data");
    if app_root.join(".git").exists()
        || app_root.join("portable.txt").is_file()
        || legacy.join("settings.json").is_file()
    {
        return legacy;
    }
    let home = PathBuf::from(if platform == "windows" {
        env("USERPROFILE").or_else(|| env("HOME"))
    } else {
        env("HOME").or_else(|| env("USERPROFILE"))
    }.unwrap_or_default());
    match platform {
        "windows" => PathBuf::from(env("LOCALAPPDATA").filter(|s| !s.is_empty()).unwrap_or_else(|| {
            home.join("AppData").join("Local").to_string_lossy().into_owned()
        })).join("Speech Studio"),
        "macos" => home.join("Library").join("Application Support").join("Speech Studio"),
        _ => {
            let base = env("XDG_DATA_HOME").map(PathBuf::from).filter(|p| p.is_absolute())
                .unwrap_or_else(|| home.join(".local").join("share"));
            base.join("speech-studio")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn relative_override_is_anchored_to_resources() {
        let root = std::env::temp_dir().join("speech-studio-path-policy");
        assert_eq!(resolve_data_dir(&root, "linux", |key| {
            (key == "SPEECHSTUDIO_DATA_DIR").then(|| "custom".into())
        }), root.join("custom"));
    }

    #[test]
    fn new_install_uses_user_data() {
        let root = std::env::temp_dir().join("speech-studio-path-policy");
        let home = std::env::temp_dir().join("speech-studio-user");
        let result = resolve_data_dir(&root, "macos", |key| {
            (key == "HOME").then(|| home.to_string_lossy().into_owned())
        });
        assert_eq!(result, home.join("Library").join("Application Support").join("Speech Studio"));
    }
}
