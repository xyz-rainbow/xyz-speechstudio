use std::ffi::c_void;
use std::sync::Once;
use std::sync::atomic::{AtomicIsize, Ordering};
use std::time::Duration;

use windows::core::Interface;
use windows::Win32::System::Com::{
    CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_INPROC_SERVER, COINIT_APARTMENTTHREADED,
};
use windows::Win32::UI::Accessibility::{
    CUIAutomation, IUIAutomation, IUIAutomationElement, IUIAutomationTextPattern, IUIAutomationTreeWalker,
    SetWinEventHook, UIA_TextPatternId, HWINEVENTHOOK,
};
use windows::Win32::UI::WindowsAndMessaging::{
    DispatchMessageW, GetClassNameW, GetGUIThreadInfo, GetMessageW, GetWindowThreadProcessId, IsWindow,
    TranslateMessage, EVENT_OBJECT_FOCUS, GUITHREADINFO, MSG, WINEVENT_OUTOFCONTEXT, WINEVENT_SKIPOWNPROCESS,
};
use windows::Win32::Foundation::HWND;

/// Last focused window that is not a popup menu and not this process.
/// Alt hotkeys (the default is Alt+NumpadMultiply) open the target app's menu
/// before UI Automation runs, so GetFocusedElement often sees the menu instead
/// of the control that still holds the selection.
static LAST_TEXT_HWND: AtomicIsize = AtomicIsize::new(0);

/// Reads the currently selected text. Never touches the clipboard.
pub fn read_selected_text() -> Option<String> {
    ensure_focus_hook();
    unsafe {
        let init = CoInitializeEx(None, COINIT_APARTMENTTHREADED);
        let inited = init.is_ok();
        let text = query_selection();
        if inited {
            CoUninitialize();
        }
        text
    }
}

fn ensure_focus_hook() {
    static START: Once = Once::new();
    START.call_once(|| {
        std::thread::spawn(|| unsafe {
            let hook = SetWinEventHook(
                EVENT_OBJECT_FOCUS,
                EVENT_OBJECT_FOCUS,
                None,
                Some(on_focus),
                0,
                0,
                WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
            );
            if hook.is_invalid() {
                return;
            }
            // Keep the hook alive. OUTOFCONTEXT events arrive on this thread.
            let mut msg = MSG::default();
            while GetMessageW(&mut msg, None, 0, 0).as_bool() {
                let _ = TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
            // SetWinEventHook stays installed until process exit. HWINEVENTHOOK
            // is Copy and does not unhook on drop.
            let _ = hook;
        });
    });
}

unsafe extern "system" fn on_focus(
    _hook: HWINEVENTHOOK,
    _event: u32,
    hwnd: HWND,
    _id_object: i32,
    _id_child: i32,
    _thread: u32,
    _time: u32,
) {
    if hwnd.0.is_null() || is_menu_class(hwnd) {
        return;
    }
    LAST_TEXT_HWND.store(hwnd.0 as isize, Ordering::Relaxed);
}

fn is_menu_class(hwnd: HWND) -> bool {
    let mut buf = [0u16; 64];
    let n = unsafe { GetClassNameW(hwnd, &mut buf) };
    if n <= 0 {
        return false;
    }
    let class = String::from_utf16_lossy(&buf[..n as usize]);
    class == "#32768" || class.eq_ignore_ascii_case("SysShadow")
}

fn query_selection() -> Option<String> {
    let automation: IUIAutomation =
        unsafe { CoCreateInstance(&CUIAutomation, None, CLSCTX_INPROC_SERVER) }.ok()?;
    let walker = unsafe { automation.RawViewWalker() }.ok();

    // A fresh COM thread often misses the first focus query. Alt may also
    // still be closing the menu, so try more than once before giving up.
    for attempt in 0..3 {
        if let Some(text) = read_once(&automation, walker.as_ref()) {
            return Some(text);
        }
        if attempt + 1 < 3 {
            std::thread::sleep(Duration::from_millis(40));
        }
    }
    None
}

fn read_once(automation: &IUIAutomation, walker: Option<&IUIAutomationTreeWalker>) -> Option<String> {
    unsafe {
        if let Ok(focused) = automation.GetFocusedElement() {
            if let Some(text) = selection_in_chain(walker, focused) {
                return Some(text);
            }
        }
    }

    for hwnd in focus_candidates() {
        let Ok(element) = (unsafe { automation.ElementFromHandle(hwnd) }) else {
            continue;
        };
        if let Some(text) = selection_in_chain(walker, element) {
            return Some(text);
        }
    }
    None
}

fn focus_candidates() -> Vec<HWND> {
    let mut out: Vec<HWND> = Vec::with_capacity(4);
    let mut push = |hwnd: HWND| {
        if hwnd.0.is_null() {
            return;
        }
        if unsafe { !IsWindow(Some(hwnd)).as_bool() } {
            return;
        }
        if is_own_process(hwnd) || is_menu_class(hwnd) {
            return;
        }
        if out.iter().any(|h| h.0 == hwnd.0) {
            return;
        }
        out.push(hwnd);
    };

    unsafe {
        let mut info = GUITHREADINFO {
            cbSize: std::mem::size_of::<GUITHREADINFO>() as u32,
            ..GUITHREADINFO::default()
        };
        if GetGUIThreadInfo(0, &mut info).is_ok() {
            // The caret window keeps the selection when Alt has moved focus to a menu.
            push(info.hwndCaret);
            push(info.hwndFocus);
        }
    }

    let cached = LAST_TEXT_HWND.load(Ordering::Relaxed);
    if cached != 0 {
        push(HWND(cached as *mut c_void));
    }
    out
}

fn is_own_process(hwnd: HWND) -> bool {
    let mut pid = 0u32;
    unsafe {
        GetWindowThreadProcessId(hwnd, Some(&raw mut pid));
    }
    pid == std::process::id()
}

fn selection_in_chain(
    walker: Option<&IUIAutomationTreeWalker>,
    mut element: IUIAutomationElement,
) -> Option<String> {
    for _ in 0..8 {
        if let Some(text) = selection_of(&element) {
            return Some(text);
        }
        let Some(walker) = walker else {
            break;
        };
        let parent = unsafe { walker.GetParentElement(&element) }.ok()?;
        if Interface::as_raw(&parent) == Interface::as_raw(&element) {
            break;
        }
        element = parent;
    }
    None
}

fn selection_of(element: &IUIAutomationElement) -> Option<String> {
    unsafe {
        let pattern = element.GetCurrentPattern(UIA_TextPatternId).ok()?;
        let text_pattern: IUIAutomationTextPattern = pattern.cast().ok()?;
        let ranges = text_pattern.GetSelection().ok()?;
        let count = ranges.Length().ok()?;
        if count <= 0 {
            return None;
        }
        let mut out = String::new();
        for i in 0..count {
            let range = ranges.GetElement(i).ok()?;
            let piece = range.GetText(-1).ok()?.to_string();
            if piece.trim().is_empty() {
                continue;
            }
            if !out.is_empty() {
                out.push(' ');
            }
            out.push_str(piece.trim());
        }
        let trimmed = out.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed.to_string())
        }
    }
}
