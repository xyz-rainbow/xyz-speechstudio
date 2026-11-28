/**
 * xyz-Ioquendo pack helpers (stable IDs for Synthesize + future Persona cards).
 * Not an official Loquendo product; redistribution blocked until license review.
 */

export const XYZ_IOQUENDO_PACK_ID = "xyz-ioquendo";
export const XYZ_IOQUENDO_REQUIRED_MODEL_ID = "qwen3-1.7b-base";
export const XYZ_IOQUENDO_REQUIRED_QUANT_ID = "Q4_K_M";
export const PACK_VOICE_PREFIX = "pack:";

export interface PackVoiceListItem {
  id: string;
  label: string;
  locale: string;
  name: string;
  pack_id: string;
  kind: "pack_reference";
}

export interface PackDependencyStatus {
  required_model_id: string;
  required_quant_id: string;
  qwen_base_installed: boolean;
  qwen_q4_installed: boolean;
  ready: boolean;
}

export interface PackInstallStatus {
  installed: boolean;
  version?: string;
  voice_count?: number;
  dependency: PackDependencyStatus;
}

export function isPackVoiceId(id: string | null | undefined): boolean {
  return Boolean(id && id.startsWith(PACK_VOICE_PREFIX));
}

export function packVoiceApiId(stableId: string): string {
  return stableId.startsWith(PACK_VOICE_PREFIX) ? stableId : `${PACK_VOICE_PREFIX}${stableId}`;
}

export function stablePackVoiceId(locale: string, slug: string): string {
  return `${XYZ_IOQUENDO_PACK_ID}/${locale}/${slug}`;
}

/** Map UI language label / code → locale filter for pack voices. */
export function localeFilterFromLanguage(language: string): string {
  const raw = (language || "").trim();
  const low = raw.toLowerCase();
  if (!raw || low === "auto" || low === "all" || low === "all languages") return "all";
  if (/^[a-z]{2,3}(-[A-Za-z0-9]{2,16})?$/i.test(raw)) return raw;
  const regionalMap: Record<string, string> = {
    "spanish (spain)": "es-ES",
    "spanish (mexico)": "es-MX",
    "spanish (argentina)": "es-AR",
    "spanish (chile)": "es-CL",
    "spanish (colombia)": "es-CO",
    "spanish (us)": "es-US",
    "spanish (peru)": "es-PE",
    "spanish (venezuela)": "es-VE",
    "english (uk)": "en-GB",
    "english (us)": "en-US",
    "english (australia)": "en-AU",
    "english (canada)": "en-CA",
    "english (ireland)": "en-IE",
    "portuguese (brazil)": "pt-BR",
    "portuguese (portugal)": "pt-PT",
    "french (france)": "fr-FR",
    "french (canada)": "fr-CA",
    "german (germany)": "de-DE",
    "german (austria)": "de-AT",
    "german (switzerland)": "de-CH",
    "italian (italy)": "it-IT",
    "catalan (spain)": "ca-ES",
    "chinese (mandarin)": "cmn",
    "chinese (cantonese)": "yue",
    "chinese (wu)": "wuu",
  };
  if (regionalMap[low]) return regionalMap[low];
  const base = low.split("(", 1)[0].trim();
  const map: Record<string, string> = {
    afrikaans: "af",
    albanian: "sq",
    amharic: "am",
    arabic: "ar",
    armenian: "hy",
    azerbaijani: "az",
    basque: "eu",
    bengali: "bn",
    bosnian: "bs",
    bulgarian: "bg",
    burmese: "my",
    catalan: "ca",
    chinese: "zh",
    croatian: "hr",
    czech: "cs",
    danish: "da",
    dutch: "nl",
    english: "en",
    estonian: "et",
    filipino: "fil",
    finnish: "fi",
    french: "fr",
    galician: "gl",
    georgian: "ka",
    german: "de",
    greek: "el",
    gujarati: "gu",
    hebrew: "he",
    hindi: "hi",
    hungarian: "hu",
    icelandic: "is",
    indonesian: "id",
    irish: "ga",
    italian: "it",
    japanese: "ja",
    javanese: "jv",
    kannada: "kn",
    kazakh: "kk",
    khmer: "km",
    korean: "ko",
    lao: "lo",
    latvian: "lv",
    lithuanian: "lt",
    macedonian: "mk",
    malay: "ms",
    malayalam: "ml",
    maltese: "mt",
    marathi: "mr",
    mongolian: "mn",
    nepali: "ne",
    norwegian: "nb",
    pashto: "ps",
    persian: "fa",
    polish: "pl",
    portuguese: "pt",
    romanian: "ro",
    russian: "ru",
    serbian: "sr",
    sinhala: "si",
    slovak: "sk",
    slovenian: "sl",
    somali: "so",
    spanish: "es",
    sundanese: "su",
    swahili: "sw",
    swedish: "sv",
    tamil: "ta",
    telugu: "te",
    thai: "th",
    turkish: "tr",
    ukrainian: "uk",
    urdu: "ur",
    uzbek: "uz",
    vietnamese: "vi",
    welsh: "cy",
    zulu: "zu",
  };
  return map[base] || raw;
}

export async function fetchXyzIoquendoStatus(baseUrl: string): Promise<PackInstallStatus> {
  const res = await fetch(`${baseUrl.replace(/\/$/, "")}/api/voice-packs/${XYZ_IOQUENDO_PACK_ID}`);
  if (!res.ok) {
    throw new Error(`xyz-Ioquendo status failed: HTTP ${res.status}`);
  }
  return (await res.json()) as PackInstallStatus;
}

export async function fetchXyzIoquendoVoices(
  baseUrl: string,
  languageOrLocale?: string,
): Promise<PackVoiceListItem[]> {
  const locale = localeFilterFromLanguage(languageOrLocale || "all");
  const url = new URL(`${baseUrl.replace(/\/$/, "")}/api/voice-packs/${XYZ_IOQUENDO_PACK_ID}/voices`);
  if (locale && locale !== "all") url.searchParams.set("locale", locale);
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`xyz-Ioquendo voices failed: HTTP ${res.status}`);
  }
  const data = (await res.json()) as { voices?: PackVoiceListItem[] };
  return data.voices ?? [];
}

export async function installXyzIoquendoFromLocalBundle(baseUrl: string): Promise<unknown> {
  const res = await fetch(
    `${baseUrl.replace(/\/$/, "")}/api/voice-packs/${XYZ_IOQUENDO_PACK_ID}/install`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Install failed: HTTP ${res.status}`);
  }
  return res.json();
}
