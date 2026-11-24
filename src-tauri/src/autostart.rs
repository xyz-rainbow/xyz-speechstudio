#[cfg(any(windows, test))]
pub(crate) fn format_windows_run_command(exe_path: &str) -> String {
    format!("\"{exe_path}\" --minimized")
}

#[cfg(any(windows, test))]
pub(crate) fn is_startup_approved_enabled(raw: &[u8]) -> bool {
    raw.first().map(|b| (b & 0x01) == 0).unwrap_or(true)
}

#[cfg(any(target_os = "linux", test))]
pub(crate) fn build_linux_desktop_entry(exe_path: &str) -> String {
    format!(
        "[Desktop Entry]\nType=Application\nName=Speech Studio\nComment=Local TTS, Voice Cloning & Live Captions\nExec=\"{exe_path}\" --minimized\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"
    )
}

#[cfg(any(target_os = "macos", test))]
pub(crate) fn build_macos_launch_agent_plist(exe_path: &str) -> String {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n<plist version=\"1.0\">\n<dict>\n  <key>Label</key>\n  <string>com.xyz.speechstudio</string>\n  <key>ProgramArguments</key>\n  <array>\n    <string>{exe_path}</string>\n    <string>--minimized</string>\n  </array>\n  <key>RunAtLoad</key>\n  <true/>\n</dict>\n</plist>\n"
    )
}

#[cfg(windows)]
mod imp {
    use std::ptr::null_mut;

    use windows::core::PCWSTR;
    use windows::Win32::Foundation::{ERROR_FILE_NOT_FOUND, ERROR_SUCCESS};
    use windows::Win32::System::Registry::{
        RegCloseKey, RegCreateKeyExW, RegDeleteValueW, RegOpenKeyExW, RegQueryValueExW,
        RegSetValueExW, HKEY, HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, KEY_WRITE, REG_BINARY,
        REG_OPTION_NON_VOLATILE, REG_SZ, REG_VALUE_TYPE,
    };

    use super::{format_windows_run_command, is_startup_approved_enabled};

    const RUN_SUBKEY: &str = "Software\\Microsoft\\Windows\\CurrentVersion\\Run";
    const APPROVED_SUBKEY: &str =
        "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\Run";
    const VALUE_NAME: &str = "Speech Studio";

    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    fn query_string_value(subkey: &str, name: &str) -> Option<String> {
        unsafe {
            let sub_w = wide(subkey);
            let name_w = wide(name);
            let mut hkey = HKEY(null_mut());
            if RegOpenKeyExW(
                HKEY_CURRENT_USER,
                PCWSTR(sub_w.as_ptr()),
                None,
                KEY_READ,
                &mut hkey,
            ) != ERROR_SUCCESS
            {
                return None;
            }
            let mut len = 0u32;
            let mut kind = REG_VALUE_TYPE(0);
            let res = RegQueryValueExW(
                hkey,
                PCWSTR(name_w.as_ptr()),
                None,
                Some(&mut kind),
                None,
                Some(&mut len),
            );
            if res != ERROR_SUCCESS || len == 0 {
                let _ = RegCloseKey(hkey);
                return None;
            }
            let mut buf = vec![0u8; len as usize];
            let res2 = RegQueryValueExW(
                hkey,
                PCWSTR(name_w.as_ptr()),
                None,
                Some(&mut kind),
                Some(buf.as_mut_ptr()),
                Some(&mut len),
            );
            let _ = RegCloseKey(hkey);
            if res2 != ERROR_SUCCESS {
                return None;
            }
            let units: Vec<u16> = buf
                .chunks_exact(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .take_while(|&u| u != 0)
                .collect();
            Some(String::from_utf16_lossy(&units))
        }
    }

    fn query_binary_value(subkey: &str, name: &str) -> Option<Vec<u8>> {
        unsafe {
            let sub_w = wide(subkey);
            let name_w = wide(name);
            let mut hkey = HKEY(null_mut());
            if RegOpenKeyExW(
                HKEY_CURRENT_USER,
                PCWSTR(sub_w.as_ptr()),
                None,
                KEY_READ,
                &mut hkey,
            ) != ERROR_SUCCESS
            {
                return None;
            }
            let mut len = 0u32;
            let mut kind = REG_VALUE_TYPE(0);
            if RegQueryValueExW(
                hkey,
                PCWSTR(name_w.as_ptr()),
                None,
                Some(&mut kind),
                None,
                Some(&mut len),
            ) != ERROR_SUCCESS
                || len == 0
            {
                let _ = RegCloseKey(hkey);
                return None;
            }
            let mut buf = vec![0u8; len as usize];
            let res2 = RegQueryValueExW(
                hkey,
                PCWSTR(name_w.as_ptr()),
                None,
                Some(&mut kind),
                Some(buf.as_mut_ptr()),
                Some(&mut len),
            );
            let _ = RegCloseKey(hkey);
            if res2 != ERROR_SUCCESS {
                None
            } else {
                Some(buf)
            }
        }
    }

    pub fn is_enabled() -> Result<bool, String> {
        let Some(val) = query_string_value(RUN_SUBKEY, VALUE_NAME) else {
            return Ok(false);
        };
        if val.trim().is_empty() {
            return Ok(false);
        }
        if let Some(approved) = query_binary_value(APPROVED_SUBKEY, VALUE_NAME) {
            return Ok(is_startup_approved_enabled(&approved));
        }
        Ok(true)
    }

    pub fn set_enabled(enabled: bool) -> Result<bool, String> {
        unsafe {
            let run_w = wide(RUN_SUBKEY);
            let app_w = wide(APPROVED_SUBKEY);
            let name_w = wide(VALUE_NAME);

            if enabled {
                let exe = std::env::current_exe().map_err(|e| e.to_string())?;
                let cmd = format_windows_run_command(&exe.to_string_lossy());
                let cmd_bytes: Vec<u8> = wide(&cmd)
                    .into_iter()
                    .flat_map(|u| u.to_le_bytes())
                    .collect();

                let mut hkey = HKEY(null_mut());
                let err = RegCreateKeyExW(
                    HKEY_CURRENT_USER,
                    PCWSTR(run_w.as_ptr()),
                    None,
                    PCWSTR::null(),
                    REG_OPTION_NON_VOLATILE,
                    KEY_WRITE,
                    None,
                    &mut hkey,
                    None,
                );
                if err != ERROR_SUCCESS {
                    return Err(format!("RegCreateKeyExW Run failed ({})", err.0));
                }
                let set_err = RegSetValueExW(
                    hkey,
                    PCWSTR(name_w.as_ptr()),
                    None,
                    REG_SZ,
                    Some(&cmd_bytes),
                );
                let _ = RegCloseKey(hkey);
                if set_err != ERROR_SUCCESS {
                    return Err(format!("RegSetValueExW Run failed ({})", set_err.0));
                }

                // Mark enabled in Task Manager StartupApproved\Run too
                let mut h_app = HKEY(null_mut());
                if RegCreateKeyExW(
                    HKEY_CURRENT_USER,
                    PCWSTR(app_w.as_ptr()),
                    None,
                    PCWSTR::null(),
                    REG_OPTION_NON_VOLATILE,
                    KEY_SET_VALUE,
                    None,
                    &mut h_app,
                    None,
                ) == ERROR_SUCCESS
                {
                    let approved_bytes = [0x02u8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
                    let _ = RegSetValueExW(
                        h_app,
                        PCWSTR(name_w.as_ptr()),
                        None,
                        REG_BINARY,
                        Some(&approved_bytes),
                    );
                    let _ = RegCloseKey(h_app);
                }
                Ok(true)
            } else {
                for sub_w in [&run_w, &app_w] {
                    let mut hkey = HKEY(null_mut());
                    if RegOpenKeyExW(
                        HKEY_CURRENT_USER,
                        PCWSTR(sub_w.as_ptr()),
                        None,
                        KEY_SET_VALUE,
                        &mut hkey,
                    ) == ERROR_SUCCESS
                    {
                        let del = RegDeleteValueW(hkey, PCWSTR(name_w.as_ptr()));
                        let _ = RegCloseKey(hkey);
                        if del != ERROR_SUCCESS && del != ERROR_FILE_NOT_FOUND {
                            return Err(format!("RegDeleteValueW failed ({})", del.0));
                        }
                    }
                }
                Ok(false)
            }
        }
    }
}

#[cfg(target_os = "linux")]
mod imp {
    use std::path::PathBuf;

    use super::build_linux_desktop_entry;

    fn entry_path() -> Result<PathBuf, String> {
        let base = std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".config")))
            .ok_or_else(|| "Could not determine user config directory".to_string())?;
        Ok(base.join("autostart").join("speech-studio.desktop"))
    }

    pub fn is_enabled() -> Result<bool, String> {
        Ok(entry_path()?.is_file())
    }

    pub fn set_enabled(enabled: bool) -> Result<bool, String> {
        let path = entry_path()?;
        if enabled {
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }
            let exe = std::env::current_exe().map_err(|e| e.to_string())?;
            let content = build_linux_desktop_entry(&exe.to_string_lossy());
            std::fs::write(&path, content).map_err(|e| e.to_string())?;
            Ok(true)
        } else {
            if path.exists() {
                std::fs::remove_file(&path).map_err(|e| e.to_string())?;
            }
            Ok(false)
        }
    }
}

#[cfg(target_os = "macos")]
mod imp {
    use std::path::PathBuf;

    use super::build_macos_launch_agent_plist;

    fn plist_path() -> Result<PathBuf, String> {
        let home = std::env::var_os("HOME")
            .map(PathBuf::from)
            .ok_or_else(|| "HOME is not set".to_string())?;
        Ok(home
            .join("Library")
            .join("LaunchAgents")
            .join("com.xyz.speechstudio.plist"))
    }

    pub fn is_enabled() -> Result<bool, String> {
        Ok(plist_path()?.is_file())
    }

    pub fn set_enabled(enabled: bool) -> Result<bool, String> {
        let path = plist_path()?;
        if enabled {
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }
            let exe = std::env::current_exe().map_err(|e| e.to_string())?;
            let content = build_macos_launch_agent_plist(&exe.to_string_lossy());
            std::fs::write(&path, content).map_err(|e| e.to_string())?;
            Ok(true)
        } else {
            if path.exists() {
                std::fs::remove_file(&path).map_err(|e| e.to_string())?;
            }
            Ok(false)
        }
    }
}

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
mod imp {
    pub fn is_enabled() -> Result<bool, String> {
        Ok(false)
    }

    pub fn set_enabled(_enabled: bool) -> Result<bool, String> {
        Err("Autostart is not supported on this platform".into())
    }
}

#[tauri::command]
pub fn get_autostart_enabled() -> Result<bool, String> {
    imp::is_enabled()
}

#[tauri::command]
pub fn set_autostart_enabled(enabled: bool) -> Result<bool, String> {
    imp::set_enabled(enabled)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn windows_run_command_quotes_exe_and_minimizes() {
        assert_eq!(
            format_windows_run_command(r"C:\Program Files\Speech Studio\speech-studio.exe"),
            "\"C:\\Program Files\\Speech Studio\\speech-studio.exe\" --minimized"
        );
    }

    #[test]
    fn startup_approved_even_byte_is_enabled_odd_is_disabled() {
        assert!(is_startup_approved_enabled(&[0x02, 0, 0, 0]));
        assert!(is_startup_approved_enabled(&[0x06, 0, 0, 0]));
        assert!(!is_startup_approved_enabled(&[0x03, 0, 0, 0]));
        assert!(!is_startup_approved_enabled(&[0x01, 0, 0, 0]));
    }

    #[test]
    fn linux_desktop_entry_contains_minimized_flag() {
        let entry = build_linux_desktop_entry("/opt/speech-studio/speech-studio");
        assert!(entry.contains("Exec=\"/opt/speech-studio/speech-studio\" --minimized"));
        assert!(entry.contains("X-GNOME-Autostart-enabled=true"));
    }

    #[test]
    fn macos_plist_contains_minimized_arg_and_run_at_load() {
        let plist = build_macos_launch_agent_plist("/Applications/Speech Studio.app/Contents/MacOS/speech-studio");
        assert!(plist.contains("<string>--minimized</string>"));
        assert!(plist.contains("<key>RunAtLoad</key>"));
    }
}
