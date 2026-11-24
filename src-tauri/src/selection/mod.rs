#[cfg(windows)]
mod windows;

#[cfg(windows)]
pub use windows::read_selected_text;

#[cfg(not(windows))]
pub fn read_selected_text() -> Option<String> {
    None
}