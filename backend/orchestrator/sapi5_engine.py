"""Native Windows SAPI 5 (32-bit + 64-bit) & OneCore TTS bridge (Loquendo TTS 7 compatible)."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path
from typing import Optional

_LOCK = threading.Lock()
_CACHE_TTL_S = 300.0
_CACHED_VOICES: list[dict[str, str]] = []
_CACHED_AT: float = 0.0
_CACHE_POPULATED: bool = False

_BASE_LANG_MAP: dict[str, str] = {
    "all": "all",
    "todo": "all",
    "todos": "all",
    "auto": "all",
    "spanish": "es",
    "español": "es",
    "english": "en",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "catalan": "ca",
    "galician": "gl",
    "basque": "eu",
    "japanese": "ja",
    "korean": "ko",
    "chinese": "zh",
    "russian": "ru",
    "dutch": "nl",
    "polish": "pl",
    "turkish": "tr",
    "arabic": "ar",
    "greek": "el",
    "swedish": "sv",
    "danish": "da",
    "finnish": "fi",
    "norwegian": "nb",
    "czech": "cs",
    "hungarian": "hu",
    "romanian": "ro",
    "hindi": "hi",
}


def is_available() -> bool:
    return sys.platform == "win32"


def _ps64_exe() -> str:
    return "powershell.exe"


def _ps32_exe() -> Optional[str]:
    win_dir = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidate = win_dir / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(candidate) if candidate.is_file() else None


def _run_ps_encoded(exe: str, script: str, timeout_s: float = 60.0) -> str:
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    run_kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout_s,
    }
    if sys.platform == "win32":
        run_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if hasattr(subprocess, "STARTUPINFO"):
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            run_kwargs["startupinfo"] = si
    proc = subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", enc],
        **run_kwargs,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"PowerShell SAPI5 failed ({proc.returncode}): {err or 'unknown error'}")
    return (proc.stdout or "").strip()


def _enum_script(reg_sources: list[tuple[str, str]]) -> str:
    lines = [
        "$ErrorActionPreference = 'SilentlyContinue'",
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
        "$script:items = @()",
        "function Dump-Cat([string]$regPath, [string]$source) {",
        "  $cat = New-Object -ComObject SAPI.SpObjectTokenCategory",
        "  $cat.SetId($regPath, $false)",
        "  $tokens = $cat.EnumerateTokens()",
        "  if (-not $tokens) { return }",
        "  for ($i = 0; $i -lt $tokens.Count; $i++) {",
        "    $tok = $tokens.Item($i)",
        "    $langAttr = $tok.GetAttribute('Language')",
        "    $langHex = if ($langAttr) { ($langAttr -split ';')[0].Trim() } else { '' }",
        "    $locale = ''; $display = ''",
        "    if ($langHex) {",
        "      try {",
        "        $ci = [System.Globalization.CultureInfo]::GetCultureInfo([Convert]::ToInt32($langHex, 16))",
        "        $locale = $ci.Name",
        "        $display = $ci.EnglishName",
        "      } catch {}",
        "    }",
        "    $script:items += [PSCustomObject]@{",
        "      source=$source; name=$tok.GetDescription(); id=$tok.Id; locale=$locale; display=$display;",
        "      vendor=$tok.GetAttribute('Vendor'); gender=$tok.GetAttribute('Gender')",
        "    }",
        "  }",
        "}",
    ]
    for path, src in reg_sources:
        lines.append(f"Dump-Cat '{path}' '{src}'")
    lines.append("ConvertTo-Json -InputObject @($script:items) -Compress")
    return "\n".join(lines)


def _clean_voice_name(name: str) -> str:
    txt = (name or "").strip()
    if " - " in txt and (txt.startswith("Microsoft ") or "Loquendo" in txt):
        left = txt.split(" - ", 1)[0].strip()
        if left:
            return left
    return txt or "SAPI5 Voice"


def _infer_locale(raw_locale: str, name: str, token_id: str) -> str:
    loc = (raw_locale or "").strip()
    if loc:
        return loc
    blob = f"{name} {token_id}".lower()
    for code, needles in (
        ("es-ES", ("castilian", "spain", "español", "espanol", "es-es", "es_es")),
        ("es-MX", ("mexican", "mexico", "méxico", "es-mx", "es_mx")),
        ("es-AR", ("argentin", "es-ar", "es_ar")),
        ("es-CL", ("chile", "es-cl", "es_cl")),
        ("es-CO", ("colombia", "es-co", "es_co")),
        ("es-US", ("us spanish", "es-us", "es_us")),
        ("ca-ES", ("catalan", "català", "valencian", "ca-es")),
        ("gl-ES", ("galician", "gallego", "gl-es")),
        ("eu-ES", ("basque", "euskera", "eu-es")),
        ("en-GB", ("british", "uk ", "en-gb")),
        ("en-US", ("american", "us ", "en-us")),
        ("fr-FR", ("french", "fr-fr")),
        ("de-DE", ("german", "de-de")),
        ("it-IT", ("italian", "it-it")),
        ("pt-BR", ("brazil", "pt-br")),
        ("pt-PT", ("portuguese", "pt-pt")),
    ):
        if any(n in blob for n in needles):
            return code
    return "und"


def _is_loquendo(item: dict[str, str]) -> bool:
    blob = f"{item.get('vendor', '')} {item.get('name', '')} {item.get('token_id', '')}".lower()
    return "loquendo" in blob


def _parse_ps_json(raw: str) -> list[dict]:
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
    except Exception:
        pass
    return []


def discover_voices(force_refresh: bool = False) -> list[dict[str, str]]:
    """Enumerate Windows SAPI 5 (64-bit + 32-bit WOW64) and OneCore voices."""
    global _CACHED_VOICES, _CACHED_AT, _CACHE_POPULATED
    if not is_available():
        return []
    now = time.time()
    with _LOCK:
        if not force_refresh and _CACHE_POPULATED and (now - _CACHED_AT) < _CACHE_TTL_S:
            return list(_CACHED_VOICES)

        rows: list[dict] = []
        try:
            raw64 = _run_ps_encoded(
                _ps64_exe(),
                _enum_script([
                    (r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices", "sapi64"),
                    (r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices", "onecore"),
                ]),
                timeout_s=15.0,
            )
            rows.extend(_parse_ps_json(raw64))
        except Exception:
            pass

        ps32 = _ps32_exe()
        if ps32:
            try:
                raw32 = _run_ps_encoded(
                    ps32,
                    _enum_script([(r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices", "sapi32")]),
                    timeout_s=15.0,
                )
                rows.extend(_parse_ps_json(raw32))
            except Exception:
                pass

        seen_desktop: set[tuple[str, str]] = set()
        seen_ids: set[str] = set()
        normalized: list[dict[str, str]] = []

        # Process 64-bit / OneCore first so sapi32 keeps unique 32-bit engines (e.g., Loquendo)
        # while avoiding duplicate standard Microsoft Desktop voices that mirror into WOW64.
        ordered_rows = [r for r in rows if r.get("source") != "sapi32"] + [
            r for r in rows if r.get("source") == "sapi32"
        ]

        for row in ordered_rows:
            src = str(row.get("source") or "sapi64").strip()
            name = str(row.get("name") or "").strip()
            token_id = str(row.get("id") or "").strip()
            if not name or not token_id:
                continue
            full_id = f"{src}|{token_id}"
            if full_id in seen_ids:
                continue
            locale = _infer_locale(str(row.get("locale") or ""), name, token_id)
            desktop_key = (name.lower(), locale.lower())
            if src == "sapi32" and desktop_key in seen_desktop:
                continue
            seen_ids.add(full_id)
            seen_desktop.add(desktop_key)

            item = {
                "id": full_id,
                "source": src,
                "token_id": token_id,
                "name": name,
                "locale": locale,
                "display": str(row.get("display") or locale),
                "vendor": str(row.get("vendor") or ""),
                "gender": str(row.get("gender") or ""),
            }
            tag = (
                f"Loquendo {'32-bit' if src == 'sapi32' else '64-bit'}"
                if _is_loquendo(item)
                else ("32-bit" if src == "sapi32" else ("OneCore" if src == "onecore" else "64-bit"))
            )
            item["label"] = f"{_clean_voice_name(name)} · {locale} [{tag}]"
            normalized.append(item)

        normalized.sort(
            key=lambda x: (
                0 if _is_loquendo(x) else (1 if x["source"] == "sapi32" else 2),
                x["locale"].lower(),
                x["name"].lower(),
            )
        )
        _CACHED_VOICES = normalized
        _CACHED_AT = now
        _CACHE_POPULATED = True
        return list(_CACHED_VOICES)


def installed_languages(force_refresh: bool = False) -> list[str]:
    voices = discover_voices(force_refresh=force_refresh)
    seen: list[str] = ["all"]
    for v in voices:
        loc = v.get("locale") or ""
        if loc and loc != "und" and loc not in seen:
            seen.append(loc)
    return seen


def _match_language_filter(voice: dict[str, str], query: Optional[str]) -> bool:
    q = (query or "").strip()
    if not q or q.lower() in ("all", "todo", "todos", "auto", "any"):
        return True
    q_low = q.lower()
    loc = (voice.get("locale") or "").lower()
    disp = (voice.get("display") or "").lower()
    if q_low == loc or q_low == disp:
        return True
    base = _BASE_LANG_MAP.get(q_low, q_low.split("-", 1)[0].split("(", 1)[0].strip())
    if loc == base or loc.startswith(f"{base}-") or loc.startswith(f"{base}_"):
        return True
    if base and disp.startswith(base):
        return True
    return False


def list_voices(language: Optional[str] = None) -> list[dict[str, str]]:
    voices = discover_voices()
    if not voices:
        return []
    matched = [v for v in voices if _match_language_filter(v, language)]
    items = matched if matched else voices
    return [{"id": v["id"], "label": v["label"], "locale": v["locale"]} for v in items]


def _resolve_voice(voice: Optional[str], language: Optional[str]) -> dict[str, str]:
    voices = discover_voices()
    if not voices:
        raise RuntimeError("No Windows SAPI 5 / OneCore voices found on this system.")
    v_str = (voice or "").strip()
    if v_str and v_str.lower() not in ("auto", "default"):
        for item in voices:
            if item["id"] == v_str or item["token_id"] == v_str or item["name"].lower() == v_str.lower():
                return item
    filtered = [v for v in voices if _match_language_filter(v, language)]
    return (filtered or voices)[0]


def synthesize_tts(*, text: str, out_path: Path, language: str = "es-ES", voice: Optional[str] = None) -> dict:
    clean = text.strip()
    if not clean:
        raise ValueError("Input text is empty.")

    target = _resolve_voice(voice, language)
    src = target["source"]
    token_id = target["token_id"]

    reg_path = (
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices"
        if src == "onecore"
        else r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices"
    )
    exe = _ps32_exe() if src == "sapi32" else _ps64_exe()
    if not exe:
        exe = _ps64_exe()

    out_path = Path(out_path).absolute()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_txt = Path(tempfile.gettempdir()) / f"ss_sapi5_{uuid.uuid4().hex[:10]}.txt"
    tmp_txt.write_text(clean, encoding="utf-8-sig")

    tok_b64 = base64.b64encode(token_id.encode("utf-8")).decode("ascii")
    out_b64 = base64.b64encode(str(out_path).encode("utf-8")).decode("ascii")
    txt_b64 = base64.b64encode(str(tmp_txt).encode("utf-8")).decode("ascii")

    script = f"""
$ErrorActionPreference = 'Stop'
$tokenId = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{tok_b64}'))
$outPath = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{out_b64}'))
$txtPath = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{txt_b64}'))
$text = [System.IO.File]::ReadAllText($txtPath, [System.Text.Encoding]::UTF8)

$cat = New-Object -ComObject SAPI.SpObjectTokenCategory
$cat.SetId('{reg_path}', $false)
$tokens = $cat.EnumerateTokens()
$chosen = $null
for ($i = 0; $i -lt $tokens.Count; $i++) {{
  $cand = $tokens.Item($i)
  if ($cand.Id -eq $tokenId) {{ $chosen = $cand; break }}
}}
if (-not $chosen) {{ throw "SAPI5 voice token not found: $tokenId" }}

$spVoice = New-Object -ComObject SAPI.SpVoice
$spVoice.Voice = $chosen
$stream = New-Object -ComObject SAPI.SpFileStream
$stream.Open($outPath, 3, $false)
try {{
  $spVoice.AudioOutputStream = $stream
  [void]$spVoice.Speak($text, 0)
}} finally {{
  $stream.Close()
}}
"""

    t0 = time.perf_counter()
    try:
        _run_ps_encoded(exe, script, timeout_s=120.0)
    finally:
        tmp_txt.unlink(missing_ok=True)

    if not out_path.is_file() or out_path.stat().st_size <= 44:
        raise RuntimeError(f"SAPI 5 produced no audio output for {target['name']}.")

    with wave.open(str(out_path), "rb") as wf:
        sr = wf.getframerate()
        dur = wf.getnframes() / float(sr) if sr else 0.0

    elapsed = time.perf_counter() - t0
    return {
        "out_path": str(out_path),
        "duration_s": round(dur, 3),
        "sr": sr,
        "elapsed_s": round(elapsed, 3),
        "rtf": round(elapsed / max(dur, 1e-4), 3),
        "engine": "sapi5",
        "backend": src,
        "voice": target["name"],
        "device": "cpu",
    }
