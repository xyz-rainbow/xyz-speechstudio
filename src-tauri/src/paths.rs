use std::path::{Path, PathBuf};

pub fn data_dir(app_root: &Path) -> PathBuf {
    resolve_data_dir(app_root, std::env::consts::OS, |key| std::env::var(key).ok())
}

pub fn cache_dir(app_root: &Path) -> PathBuf {
    resolve_cache_dir(app_root, std::env::consts::OS, |key| std::env::var(key).ok())
}

pub fn ensure_user_dirs(data: &Path, cache: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(data)?;
    for name in ["models", "profiles", "outputs", "tmp", "cache", "updates"] {
        std::fs::create_dir_all(data.join(name))?;
    }
    if cache != data.join("cache") {
        std::fs::create_dir_all(cache)?;
    }
    Ok(())
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

fn resolve_cache_dir(
    app_root: &Path,
    platform: &str,
    env: impl Fn(&str) -> Option<String>,
) -> PathBuf {
    if let Some(value) = env("SPEECHSTUDIO_CACHE_DIR").filter(|s| !s.trim().is_empty()) {
        let path = PathBuf::from(value.trim());
        return if path.is_absolute() { path } else { app_root.join(path) };
    }
    let data = resolve_data_dir(app_root, platform, &env);
    if data == app_root.join("data") || app_root.join("portable.txt").is_file() {
        return data.join("cache");
    }
    let home = PathBuf::from(if platform == "windows" {
        env("USERPROFILE").or_else(|| env("HOME"))
    } else {
        env("HOME").or_else(|| env("USERPROFILE"))
    }.unwrap_or_default());
    match platform {
        "windows" => PathBuf::from(env("LOCALAPPDATA").filter(|s| !s.is_empty()).unwrap_or_else(|| {
            home.join("AppData").join("Local").to_string_lossy().into_owned()
        })).join("Speech Studio").join("cache"),
        "macos" => home.join("Library").join("Caches").join("Speech Studio"),
        _ => {
            let base = env("XDG_CACHE_HOME").map(PathBuf::from).filter(|p| p.is_absolute())
                .unwrap_or_else(|| home.join(".cache"));
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

    #[test]
    fn unicode_and_brackets_survive_override() {
        let root = std::env::temp_dir().join("speech-studio-[tools]-path");
        let fancy = root.join("datos-áéí").join("Speech Studio");
        let resolved = resolve_data_dir(&root, "windows", |key| {
            (key == "SPEECHSTUDIO_DATA_DIR").then(|| fancy.to_string_lossy().into_owned())
        });
        assert_eq!(resolved, fancy);
    }

    #[test]
    fn cache_defaults_under_xdg_on_linux() {
        let root = std::env::temp_dir().join("speech-studio-cache-policy");
        let home = std::env::temp_dir().join("speech-studio-cache-home");
        let cache = resolve_cache_dir(&root, "linux", |key| match key {
            "HOME" => Some(home.to_string_lossy().into_owned()),
            _ => None,
        });
        assert_eq!(cache, home.join(".cache").join("speech-studio"));
    }
}
