use serde::Serialize;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(windows)]
mod windows;

pub fn initialize() {
    #[cfg(windows)]
    windows::ensure_focus_hook();
}

/// `code` is `text`, `empty`, or `unavailable`.
/// `unavailable` means the Linux primary-selection tools are missing.
/// It does not mean the clipboard was read.
#[derive(Serialize, Clone)]
pub struct SelectionPayload {
    pub text: String,
    pub code: String,
}

impl SelectionPayload {
    #[cfg_attr(not(any(windows, target_os = "linux")), allow(dead_code))]
    pub(crate) fn text(text: String) -> Self {
        Self {
            text,
            code: "text".into(),
        }
    }

    pub(crate) fn empty() -> Self {
        Self {
            text: String::new(),
            code: "empty".into(),
        }
    }

    /// Linux calls this when neither wl-paste nor xclip is installed.
    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub(crate) fn unavailable() -> Self {
        Self {
            text: String::new(),
            code: "unavailable".into(),
        }
    }

    /// macOS (and other platforms) without a selection backend.
    #[cfg_attr(not(target_os = "macos"), allow(dead_code))]
    pub(crate) fn unsupported() -> Self {
        Self {
            text: String::new(),
            code: "unsupported".into(),
        }
    }
}

pub fn read_selection() -> SelectionPayload {
    #[cfg(windows)]
    {
        match windows::read_selected_text() {
            Some(text) if !text.trim().is_empty() => SelectionPayload::text(text),
            _ => SelectionPayload::empty(),
        }
    }
    #[cfg(target_os = "linux")]
    {
        linux::read_primary_selection()
    }
    #[cfg(target_os = "macos")]
    {
        // No Accessibility selection reader yet — distinct from Linux missing tools.
        SelectionPayload::unsupported()
    }
    #[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
    {
        SelectionPayload::empty()
    }
}
