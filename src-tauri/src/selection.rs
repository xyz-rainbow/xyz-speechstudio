use windows::core::Interface;
use windows::Win32::System::Com::{
    CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_INPROC_SERVER, COINIT_APARTMENTTHREADED,
};
use windows::Win32::UI::Accessibility::{
    CUIAutomation, IUIAutomation, IUIAutomationTextPattern, UIA_TextPatternId,
};

/// Reads the currently selected text of the focused control using Windows UI Automation.
/// Never touches the clipboard. Returns None when the focused app does not expose TextPattern.
pub fn read_selected_text() -> Option<String> {
    unsafe {
        let init = CoInitializeEx(None, COINIT_APARTMENTTHREADED);
        let inited = init.is_ok();

        let result = (|| -> windows::core::Result<String> {
            let automation: IUIAutomation = CoCreateInstance(&CUIAutomation, None, CLSCTX_INPROC_SERVER)?;
            let element = automation.GetFocusedElement()?;
            let pattern = element.GetCurrentPattern(UIA_TextPatternId)?;
            let text_pattern: IUIAutomationTextPattern = pattern.cast()?;
            let ranges = text_pattern.GetSelection()?;
            let count = ranges.Length()?;
            let mut out = String::new();
            for i in 0..count {
                let range = ranges.GetElement(i)?;
                let bstr = range.GetText(-1)?;
                if !out.is_empty() {
                    out.push(' ');
                }
                out.push_str(&bstr.to_string());
            }
            Ok(out)
        })();

        if inited {
            CoUninitialize();
        }

        match result {
            Ok(s) if !s.trim().is_empty() => Some(s.trim().to_string()),
            _ => None,
        }
    }
}
