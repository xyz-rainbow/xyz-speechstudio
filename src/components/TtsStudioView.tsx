import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { save as saveDialog } from "@tauri-apps/plugin-dialog";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  Eraser,
  FolderArchive,
  FolderOpen,
  Loader2,
  Play,
  Save,
  Trash2,
} from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import {
  cancelTtsSynthesis,
  clearPlaySession,
  deleteHistoryRecord,
  fetchBuiltinVoices,
  fetchModelsCatalog,
  isTauri,
  LiveCaptionsConflictError,
  notify,
  revealInExplorer,
  saveHistoryAs,
  savePlaySession,
  startPlaySession,
  synthesizeSessionChunk,
  synthesizeTts,
  uninstallLanguagePack,
} from "../services/api";
import type {
  AppSettings,
  CatalogModelEntry,
  GenerationRecord,
  VoiceProfile,
} from "../types";
import { endpointProviderSubtitle } from "../utils/endpointPresets";
import { BorderBeamButton } from "./BorderBeamButton";
import {
  ChunkedAudioPlayer,
  type AudioChunkItem,
  type ChunkedAudioPlayerHandle,
  type PlaybackIslandState,
} from "./ChunkedAudioPlayer";
import { GlassCard } from "./GlassCard";

interface TtsStudioViewProps {
  baseUrl: string;
  catalog: CatalogModelEntry[];
  settings: AppSettings;
  onSaveSettings: (next: AppSettings) => Promise<void>;
  profiles: VoiceProfile[];
  selectedProfileId: string;
  onSelectProfileId: (id: string) => void;
  history: GenerationRecord[];
  onHistoryChange: (next: GenerationRecord[]) => void;
  onAfterGpuAction: () => void;
  incomingSpeak?: { text: string; nonce: number } | null;
  notificationsEnabled: boolean;
  onOpenModels?: () => void;
  onOpenProfiles?: () => void;
  onCatalogChange?: (models: CatalogModelEntry[]) => void;
  onInstalledLanguagesChange?: (next: Record<string, string[]>) => void;
  onPlaybackStateChange?: (state: PlaybackIslandState) => void;
  playerHandleRef?: React.MutableRefObject<ChunkedAudioPlayerHandle | null>;
}

/** ISO/BCP-47 code → display label. Includes regional dialects for SAPI 5 / Loquendo. */
const LANG_CODE_TO_LABEL: Record<string, string> = {
  all: "All Languages",
  es: "Spanish",
  "es-ES": "Spanish (Spain)",
  "es-MX": "Spanish (Mexico)",
  "es-AR": "Spanish (Argentina)",
  "es-CL": "Spanish (Chile)",
  "es-CO": "Spanish (Colombia)",
  "es-US": "Spanish (US)",
  "es-PE": "Spanish (Peru)",
  "es-VE": "Spanish (Venezuela)",
  en: "English",
  "en-US": "English (US)",
  "en-GB": "English (UK)",
  "en-AU": "English (Australia)",
  "en-CA": "English (Canada)",
  "en-IE": "English (Ireland)",
  fr: "French",
  "fr-FR": "French (France)",
  "fr-CA": "French (Canada)",
  de: "German",
  "de-DE": "German (Germany)",
  "de-AT": "German (Austria)",
  "de-CH": "German (Switzerland)",
  it: "Italian",
  "it-IT": "Italian (Italy)",
  pt: "Portuguese",
  "pt-BR": "Portuguese (Brazil)",
  "pt-PT": "Portuguese (Portugal)",
  ca: "Catalan",
  "ca-ES": "Catalan (Spain)",
  gl: "Galician",
  "gl-ES": "Galician (Spain)",
  eu: "Basque",
  "eu-ES": "Basque (Spain)",
  ja: "Japanese",
  "ja-JP": "Japanese (Japan)",
  ko: "Korean",
  "ko-KR": "Korean (Korea)",
  zh: "Chinese",
  "zh-CN": "Chinese (Simplified)",
  "zh-TW": "Chinese (Traditional)",
  ru: "Russian",
  "ru-RU": "Russian (Russia)",
  hi: "Hindi",
  "hi-IN": "Hindi (India)",
  ar: "Arabic",
  "ar-SA": "Arabic (Saudi Arabia)",
  nl: "Dutch",
  "nl-NL": "Dutch (Netherlands)",
  pl: "Polish",
  "pl-PL": "Polish (Poland)",
  tr: "Turkish",
  "tr-TR": "Turkish (Turkey)",
  el: "Greek",
  "el-GR": "Greek (Greece)",
  ro: "Romanian",
  "ro-RO": "Romanian (Romania)",
  da: "Danish",
  "da-DK": "Danish (Denmark)",
  fi: "Finnish",
  "fi-FI": "Finnish (Finland)",
  sv: "Swedish",
  "sv-SE": "Swedish (Sweden)",
  nb: "Norwegian",
  "nb-NO": "Norwegian (Norway)",
  sw: "Swahili",
  cs: "Czech",
  "cs-CZ": "Czech (Czechia)",
  hu: "Hungarian",
  "hu-HU": "Hungarian (Hungary)",
};

const LABEL_TO_CODE: Record<string, string> = Object.fromEntries(
  Object.entries(LANG_CODE_TO_LABEL).map(([code, label]) => [label, code]),
);

const FALLBACK_LANGUAGES = Object.values(LANG_CODE_TO_LABEL);

function normalizeTtsModelId(id: string): string {
  if (id.startsWith("qwen3-1.7b-base")) return "qwen3-1.7b-base";
  if (id.startsWith("qwen3-1.7b-customvoice")) return "qwen3-1.7b-customvoice";
  if (id.startsWith("qwen3-0.6b-base")) return "qwen3-0.6b-base";
  if (id.startsWith("xtts")) return "xtts-v2";
  return id;
}

function labelForCode(code: string): string {
  return LANG_CODE_TO_LABEL[code] || code;
}

export const TtsStudioView: React.FC<TtsStudioViewProps> = ({
  baseUrl,
  catalog,
  settings,
  onSaveSettings,
  profiles,
  selectedProfileId,
  onSelectProfileId,
  history,
  onHistoryChange,
  onAfterGpuAction,
  incomingSpeak,
  notificationsEnabled,
  onOpenModels,
  onOpenProfiles,
  onCatalogChange,
  onInstalledLanguagesChange,
  onPlaybackStateChange,
  playerHandleRef,
}) => {
  const { t } = useI18n();
  const [subView, setSubView] = useState<"editor" | "exported">("editor");
  const [text, setText] = useState("");
  const [language, setLanguage] = useState("Spanish");
  const [busyMode, setBusyMode] = useState<"play" | "wav" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingForceMode, setPendingForceMode] = useState<"play" | "wav" | null>(null);
  const [exportedPreviewUrl, setExportedPreviewUrl] = useState<string | null>(null);
  const [exportedPlayNonce, setExportedPlayNonce] = useState(0);
  const [playChunks, setPlayChunks] = useState<AudioChunkItem[]>([]);
  const [isGeneratingSession, setIsGeneratingSession] = useState(false);
  const [autoPlayNonce, setAutoPlayNonce] = useState(0);
  const [lastStats, setLastStats] = useState<{ dur: number; elapsed: number; rtf: number } | null>(
    null
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPos, setMenuPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const [langMenuPos, setLangMenuPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const [langBusy, setLangBusy] = useState(false);
  const [builtinVoices, setBuiltinVoices] = useState<{ id: string; label: string }[]>([]);
  const [selectedBuiltinVoice, setSelectedBuiltinVoice] = useState<string>("");
  const menuRef = useRef<HTMLDivElement | null>(null);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const langMenuRef = useRef<HTMLDivElement | null>(null);
  const langDropdownRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<ChunkedAudioPlayerHandle | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const sessionSigRef = useRef<string>("");
  const prefetchAbortRef = useRef<AbortController | null>(null);
  const prefetchPromiseRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    if (playerHandleRef) {
      playerHandleRef.current = playerRef.current;
    }
  });
  const catalogTts = React.useMemo(
    () =>
      catalog.filter(
        (m) =>
          m.kind === "tts" &&
          m.installed &&
          (m.runtime_supported || m.capabilities?.voice_mode === "builtin_voices"),
      ),
    [catalog]
  );

  useEffect(() => {
    if (!menuOpen && !langMenuOpen) return;
    const onPointerDown = (ev: MouseEvent) => {
      const target = ev.target as Node;
      if (
        menuOpen &&
        menuRef.current &&
        !menuRef.current.contains(target) &&
        !dropdownRef.current?.contains(target)
      ) {
        setMenuOpen(false);
      }
      if (
        langMenuOpen &&
        langMenuRef.current &&
        !langMenuRef.current.contains(target) &&
        !langDropdownRef.current?.contains(target)
      ) {
        setLangMenuOpen(false);
      }
    };
    window.addEventListener("mousedown", onPointerDown);
    return () => window.removeEventListener("mousedown", onPointerDown);
  }, [menuOpen, langMenuOpen]);

  useEffect(() => {
    if (!menuOpen) {
      setMenuPos(null);
      return;
    }
    const updatePos = () => {
      const el = menuRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const width = 280;
      const rawLeft = rect.left + rect.width / 2 - width / 2;
      const left = Math.max(12, Math.min(window.innerWidth - width - 12, rawLeft));
      setMenuPos({
        top: rect.bottom + 6,
        left,
        width,
      });
    };
    updatePos();
    window.addEventListener("resize", updatePos);
    return () => window.removeEventListener("resize", updatePos);
  }, [menuOpen]);

  useEffect(() => {
    if (!langMenuOpen) {
      setLangMenuPos(null);
      return;
    }
    const updateLangPos = () => {
      const el = langMenuRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const width = Math.max(192, rect.width);
      const left = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left));
      setLangMenuPos({ top: rect.bottom + 6, left, width });
    };
    updateLangPos();
    window.addEventListener("resize", updateLangPos);
    return () => window.removeEventListener("resize", updateLangPos);
  }, [langMenuOpen]);

  // Keep TTS catalog fresh while this view stays mounted across tabs.
  useEffect(() => {
    if (!baseUrl || !onCatalogChange) return;
    let cancelled = false;
    void fetchModelsCatalog(baseUrl)
      .then((res) => {
        if (!cancelled) onCatalogChange(res.models);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [baseUrl, settings.active_tts_model, onCatalogChange]);

  const activeModelId = normalizeTtsModelId(settings.active_tts_model || "qwen3-1.7b-base");
  const isEndpointMode = settings.tts_source === "endpoint";
  const ttsEndpoints = settings.external_endpoints.filter((e) => e.kind === "tts");
  const activeEp = ttsEndpoints.find((e) => e.id === settings.active_tts_endpoint_id);

  const activeEntry = React.useMemo(() => {
    const raw = settings.active_tts_model || "";
    return (
      catalog.find((m) => m.id === raw) ||
      catalog.find((m) => m.id === activeModelId) ||
      catalog.find((m) => normalizeTtsModelId(m.id) === activeModelId) ||
      catalogTts[0] ||
      null
    );
  }, [catalog, catalogTts, settings.active_tts_model, activeModelId]);

  const installMode = activeEntry?.capabilities?.install_mode ?? "shared_weights";
  const voiceMode = activeEntry?.capabilities?.voice_mode ?? "clone_profile";
  const usesCloneProfiles = !isEndpointMode && voiceMode === "clone_profile";
  const usesBuiltinVoices = !isEndpointMode && voiceMode === "builtin_voices";

  useEffect(() => {
    if (!baseUrl || !usesBuiltinVoices || !activeEntry?.id) {
      setBuiltinVoices([]);
      setSelectedBuiltinVoice("");
      return;
    }
    let cancelled = false;
    void fetchBuiltinVoices(baseUrl, activeEntry.id, language)
      .then((list) => {
        if (cancelled) return;
        setBuiltinVoices(list);
        setSelectedBuiltinVoice((cur) =>
          list.some((v) => v.id === cur) ? cur : list[0]?.id || ""
        );
      })
      .catch(() => {
        if (!cancelled) setBuiltinVoices([]);
      });
    return () => {
      cancelled = true;
    };
  }, [baseUrl, usesBuiltinVoices, activeEntry?.id, language]);
  const showLangTrash =
    !isEndpointMode &&
    (installMode === "per_language_checkpoint" || installMode === "voices_pack");

  const readyLanguageCodes = React.useMemo(() => {
    if (isEndpointMode || !activeEntry) return [];
    const caps = activeEntry.capabilities?.languages ?? [];
    if (installMode === "shared_weights") {
      return activeEntry.installed || activeEntry.runtime_supported ? caps : [];
    }
    const familyId = activeEntry.family_id;
    const fromSettings = settings.installed_languages?.[familyId] ?? [];
    const fromVariants = catalog
      .filter((m) => m.family_id === familyId && m.installed)
      .flatMap((m) => m.capabilities?.languages ?? []);
    const ready = new Set([...fromSettings, ...fromVariants]);
    return caps.filter((code) => ready.has(code));
  }, [
    isEndpointMode,
    activeEntry,
    installMode,
    settings.installed_languages,
    catalog,
  ]);

  const availableLanguages = React.useMemo(() => {
    if (isEndpointMode) return FALLBACK_LANGUAGES;
    if (readyLanguageCodes.length > 0) {
      return readyLanguageCodes.map(labelForCode);
    }
    // Shared clone engines without caps metadata: keep legacy list.
    if (installMode === "shared_weights" && usesCloneProfiles) {
      return FALLBACK_LANGUAGES;
    }
    return [];
  }, [isEndpointMode, readyLanguageCodes, installMode, usesCloneProfiles]);

  const localOptions: {
    id: string;
    name: string;
    subtitle: string;
    engine: string;
    runtime_supported: boolean;
  }[] = React.useMemo(
    () =>
      catalogTts.map((m) => ({
        id: m.id,
        name: m.name,
        subtitle: `${m.installed_quant || m.quants[0]?.id || m.engine} · ~${(
          m.vram_mib / 1024
        ).toFixed(1)} GB${!m.runtime_supported ? " · no runtime" : ""}`,
        engine: m.engine,
        runtime_supported: m.runtime_supported,
      })),
    [catalogTts]
  );

  const activeLocal = localOptions.find((m) => m.id === activeEntry?.id) || localOptions[0];
  const modelFamily = (() => {
    const eng = activeEntry?.engine || activeLocal?.engine || "";
    if (eng === "xtts" || (activeLocal?.id || activeModelId).startsWith("xtts")) return "xtts";
    if (eng === "qwen" || eng.startsWith("qwen")) return "qwen";
    if (eng === "f5" || eng === "f5-tts") return "f5";
    if (eng === "fish" || eng === "fish-audio") return "fish";
    return eng || "qwen";
  })();
  const visibleProfiles = usesCloneProfiles
    ? profiles.filter((p) => {
        if (p.engine === modelFamily || (modelFamily === "qwen" && p.engine === "qwen")) {
          return true;
        }
        // Fish Speech and F5 clone from the reference wav. A profile tagged
        // chatterbox (or another clone engine) is still a valid voice.
        if ((modelFamily === "fish" || modelFamily === "f5") && p.ref_audio_path) return true;
        return false;
      })
    : [];
  const selectedProfile =
    visibleProfiles.find((p) => p.id === selectedProfileId) || visibleProfiles[0];

  const selectorLabel = isEndpointMode
    ? `${t("models.externalGroup")} · ${activeEp ? activeEp.name : t("transcriber.unconfigured")}`
    : activeLocal
      ? `${t("models.local")} · ${activeLocal.name}`
      : `${t("models.local")} · ${t("models.noLocalInstalled")}`;

  const selectLocalModel = async (id: string) => {
    setMenuOpen(false);
    if (settings.tts_source === "local" && settings.active_tts_model === id) {
      return;
    }
    await onSaveSettings({
      ...settings,
      tts_source: "local",
      active_tts_model: id,
    });
  };

  const selectEndpoint = async (id: string) => {
    setMenuOpen(false);
    if (settings.tts_source === "endpoint" && settings.active_tts_endpoint_id === id) {
      return;
    }
    await onSaveSettings({
      ...settings,
      tts_source: "endpoint",
      active_tts_endpoint_id: id,
    });
  };

  const removeReadyLanguage = async (code: string) => {
    if (!baseUrl || !activeEntry || !showLangTrash) return;
    if (installMode !== "per_language_checkpoint" && installMode !== "voices_pack") return;
    setLangBusy(true);
    setError(null);
    try {
      const res = await uninstallLanguagePack(
        baseUrl,
        activeEntry.family_id,
        code,
        installMode,
      );
      onInstalledLanguagesChange?.(res.installed_languages);
      if (onCatalogChange) {
        const cat = await fetchModelsCatalog(baseUrl);
        onCatalogChange(cat.models);
      }
      const nextLabels = (activeEntry.capabilities?.languages ?? [])
        .filter((c) => (res.installed_languages[activeEntry.family_id] ?? []).includes(c))
        .map(labelForCode);
      if (!nextLabels.includes(language)) {
        setLanguage(nextLabels[0] || "Spanish");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLangBusy(false);
    }
  };

  useEffect(() => {
    if (!usesCloneProfiles) return;
    if (visibleProfiles.some((p) => p.id === selectedProfileId)) return;
    if (visibleProfiles[0]) onSelectProfileId(visibleProfiles[0].id);
  }, [
    activeModelId,
    profiles,
    selectedProfileId,
    onSelectProfileId,
    visibleProfiles,
    usesCloneProfiles,
  ]);

  useEffect(() => {
    if (usesCloneProfiles && selectedProfile) {
      const profLang = (selectedProfile.language || "").trim();
      if (profLang && profLang.toLowerCase() !== "auto") {
        setLanguage(profLang);
      } else if (availableLanguages.length > 0 && !availableLanguages.includes(language)) {
        setLanguage(availableLanguages[0]);
      }
      return;
    }
    if (availableLanguages.length > 0 && !availableLanguages.includes(language)) {
      const base = language.split("(", 1)[0].trim().toLowerCase();
      const partial = availableLanguages.find((lbl) => lbl.toLowerCase().startsWith(base));
      setLanguage(partial || availableLanguages[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync when catalog readiness or profile changes
  }, [selectedProfile?.id, usesCloneProfiles, availableLanguages]);

  const synthTokenRef = useRef(0);
  const lastSpokenRef = useRef("");

  const canSynthesize =
    !busyMode &&
    !!text.trim() &&
    (isEndpointMode
      ? !!activeEp
      : usesCloneProfiles
        ? !!activeLocal?.runtime_supported && !!selectedProfile
        : usesBuiltinVoices
          ? !!activeLocal?.runtime_supported && availableLanguages.length > 0
          : false);

  const buildSessionSignature = (targetText: string) =>
    [
      targetText.trim(),
      settings.tts_source,
      settings.active_tts_model,
      settings.active_tts_endpoint_id,
      selectedProfile?.id || "",
      selectedBuiltinVoice,
      language,
      settings.tts_chunk_enabled ? "1" : "0",
      String(settings.tts_chunk_max_chars),
    ].join("||");

  const runSynth = async (
    mode: "play" | "wav",
    forceStopCaptions = false,
    textOverride?: string
  ) => {
    if (!baseUrl) return;
    if (isEndpointMode && !activeEp) return;
    if (!isEndpointMode && usesCloneProfiles && !selectedProfile) return;
    if (!isEndpointMode && usesBuiltinVoices && !activeLocal?.runtime_supported) return;

    const targetText = textOverride ?? text;
    const myToken = ++synthTokenRef.current;
    const profileId = selectedProfile?.id || (usesBuiltinVoices ? "builtin" : "mario");
    const voiceParam = usesBuiltinVoices && selectedBuiltinVoice ? selectedBuiltinVoice : undefined;
    const sig = buildSessionSignature(targetText);

    setBusyMode(mode);
    setError(null);
    setPendingForceMode(null);

    try {
      if (mode === "play") {
        lastSpokenRef.current = targetText.trim();
        prefetchAbortRef.current?.abort();
        playerRef.current?.pause();
        const abort = new AbortController();
        prefetchAbortRef.current = abort;

        const started = await startPlaySession(baseUrl, {
          profile_id: profileId,
          text: targetText,
          language,
          voice: voiceParam,
          force_stop_captions: forceStopCaptions,
        });
        if (myToken !== synthTokenRef.current || abort.signal.aborted) return;

        const initialChunks: AudioChunkItem[] = started.chunks.map((chunkText, idx) => ({
          index: idx,
          text: chunkText,
        }));
        sessionIdRef.current = started.session_id;
        sessionSigRef.current = sig;
        setPlayChunks(initialChunks);
        setIsGeneratingSession(started.chunks.length > 1);

        // Synthesize first chunk immediately so playback starts fast.
        const firstRes = await synthesizeSessionChunk(
          baseUrl,
          started.session_id,
          0,
          forceStopCaptions,
          abort.signal
        );
        if (myToken !== synthTokenRef.current || abort.signal.aborted) return;

        setPlayChunks((prev) =>
          prev.map((item) =>
            item.index === 0
              ? {
                  ...item,
                  audioUrl: `${baseUrl}${firstRes.audio_url}`,
                  durationS: firstRes.duration_s,
                }
              : item
          )
        );
        setLastStats({
          dur: firstRes.duration_s,
          elapsed: firstRes.elapsed_s,
          rtf: firstRes.rtf,
        });
        setBusyMode(null);
        setAutoPlayNonce((n) => n + 1);
        void notify(notificationsEnabled, t("toast.title"), t("toast.playing"));

        if (started.chunks.length > 1) {
          const prefetchJob = (async () => {
            let totalDur = firstRes.duration_s;
            let totalElapsed = firstRes.elapsed_s;
            for (let i = 1; i < started.chunks.length; i++) {
              if (myToken !== synthTokenRef.current || abort.signal.aborted) return;
              const chunkRes = await synthesizeSessionChunk(
                baseUrl,
                started.session_id,
                i,
                forceStopCaptions,
                abort.signal
              );
              if (myToken !== synthTokenRef.current || abort.signal.aborted) return;
              totalDur += chunkRes.duration_s;
              totalElapsed += chunkRes.elapsed_s;
              setPlayChunks((prev) =>
                prev.map((item) =>
                  item.index === i
                    ? {
                        ...item,
                        audioUrl: `${baseUrl}${chunkRes.audio_url}`,
                        durationS: chunkRes.duration_s,
                      }
                    : item
                )
              );
              setLastStats({
                dur: totalDur,
                elapsed: totalElapsed,
                rtf: totalDur > 0 ? totalElapsed / totalDur : 0,
              });
            }
          })()
            .catch(() => {
              // Aborted or failed mid-prefetch.
            })
            .finally(() => {
              if (myToken === synthTokenRef.current) {
                setIsGeneratingSession(false);
                onAfterGpuAction();
              }
            });
          prefetchPromiseRef.current = prefetchJob;
        } else {
          setIsGeneratingSession(false);
          onAfterGpuAction();
        }
        return;
      }

      // Smart Save ("wav"): reuse existing generated session chunks if signature matches;
      // otherwise synthesize full text directly as a single file in outputs_dir.
      if (sessionIdRef.current && sessionSigRef.current === sig) {
        if (prefetchPromiseRef.current) {
          await prefetchPromiseRef.current;
        }
        if (myToken !== synthTokenRef.current) return;
        const saved = await savePlaySession(baseUrl, sessionIdRef.current, forceStopCaptions);
        if (myToken !== synthTokenRef.current) return;
        onHistoryChange([saved.record, ...history]);
        setLastStats({
          dur: saved.record.duration_s,
          elapsed: saved.record.elapsed_s,
          rtf: saved.record.rtf,
        });
        void notify(notificationsEnabled, t("toast.title"), t("toast.saved"));
        onAfterGpuAction();
        return;
      }

      const res = await synthesizeTts(baseUrl, {
        profile_id: profileId,
        text: targetText,
        language,
        voice: voiceParam,
        mode: "wav",
        force_stop_captions: forceStopCaptions,
      });
      if (myToken !== synthTokenRef.current) return;
      if (res.record) {
        onHistoryChange([res.record, ...history]);
        setLastStats({
          dur: res.record.duration_s,
          elapsed: res.record.elapsed_s,
          rtf: res.record.rtf,
        });
      }
      void notify(notificationsEnabled, t("toast.title"), t("toast.saved"));
      onAfterGpuAction();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      if (err instanceof LiveCaptionsConflictError) {
        setPendingForceMode(mode);
      } else {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        void notify(notificationsEnabled, t("toast.title"), t("toast.failed"));
      }
    } finally {
      setBusyMode(null);
    }
  };

  // Global hotkey "read selection": toggle pause/resume on same text, otherwise stop and play the new text.
  useEffect(() => {
    if (!incomingSpeak) return;
    const incoming = incomingSpeak.text.trim();
    const isPlaying = playerRef.current?.isPlaying() ?? false;
    const isPaused = playerRef.current?.isPausedMidway() ?? false;
    const sameText = incoming === "" || incoming === lastSpokenRef.current;

    if (sameText && isPlaying) {
      playerRef.current?.pause();
      return;
    }
    if (sameText && isPaused) {
      playerRef.current?.togglePlay();
      void notify(notificationsEnabled, t("toast.title"), t("toast.playing"));
      return;
    }
    if (incoming === "") {
      if (!isPlaying && !isPaused) {
        void notify(notificationsEnabled, t("toast.title"), t("hotkey.noSelection"));
      }
      return;
    }

    playerRef.current?.pause();
    void notify(notificationsEnabled, t("toast.title"), t("hotkey.processing"));
    setSubView("editor");
    setText(incoming);
    lastSpokenRef.current = incoming;
    void runSynth("play", false, incoming);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incomingSpeak?.nonce]);

  const handleSaveAs = async (rec: GenerationRecord) => {
    if (!baseUrl || !isTauri()) return;
    const dest = await saveDialog({
      defaultPath: `${rec.profile_name.toLowerCase()}-${rec.id}.wav`,
      filters: [{ name: "WAV Audio", extensions: ["wav"] }],
    });
    if (!dest) return;
    const updated = await saveHistoryAs(baseUrl, rec.id, dest);
    onHistoryChange(history.map((h) => (h.id === rec.id ? updated : h)));
    void notify(notificationsEnabled, t("toast.title"), t("toast.saved"));
  };

  const handleReveal = async (rec: GenerationRecord) => {
    await revealInExplorer(rec.saved_path || rec.file_path);
  };

  const handleDelete = async (rec: GenerationRecord) => {
    if (!baseUrl) return;
    await deleteHistoryRecord(baseUrl, rec.id);
    onHistoryChange(history.filter((h) => h.id !== rec.id));
    void notify(notificationsEnabled, t("toast.title"), t("toast.deletedAudio"));
  };

  if (subView === "exported") {
    return (
      <div className="flex-1 min-h-0 flex flex-col">
        <GlassCard className="flex-1 min-h-0 p-4 flex flex-col gap-3 overflow-hidden">
          <div className="flex items-center justify-between gap-2 shrink-0">
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() => setSubView("editor")}
                className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium hover:border-purple-400/50 transition-colors"
                style={{
                  backgroundColor: "var(--bg-elevated)",
                  borderColor: "var(--border-glass)",
                }}
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                {t("synthesize.back")}
              </button>
              <h1 className="text-base font-semibold">
                {t("synthesize.historyTitle")} ({history.length})
              </h1>
            </div>
          </div>

          {exportedPreviewUrl && (
            <ChunkedAudioPlayer
              chunks={[]}
              singleUrl={exportedPreviewUrl}
              autoPlayNonce={exportedPlayNonce}
            />
          )}

          <div className="flex-1 min-h-0 overflow-y-auto pr-1 flex flex-col gap-2">
            {history.length === 0 ? (
              <div
                className="flex-1 flex items-center justify-center text-xs rounded-2xl border p-6"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-input)",
                  color: "var(--text-muted)",
                }}
              >
                {t("synthesize.emptyHistory")}
              </div>
            ) : (
              history.map((rec) => {
                const url = `${baseUrl}/api/tts/history/${rec.id}/audio`;
                return (
                  <div
                    key={rec.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border px-3 py-2"
                    style={{
                      backgroundColor: "var(--bg-input)",
                      borderColor: "var(--border-glass)",
                    }}
                  >
                    <div className="flex-1 min-w-[180px]">
                      <div className="flex items-center gap-2 text-xs">
                        <span className="font-semibold text-purple-300">{rec.profile_name}</span>
                        <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
                          {rec.duration_s.toFixed(2)}s · RTF {rec.rtf.toFixed(2)}
                        </span>
                        {rec.saved_path && (
                          <span className="rounded-full px-2 py-0.5 text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                            {t("synthesize.savedAt")}
                          </span>
                        )}
                      </div>
                      <p className="text-xs truncate mt-0.5" style={{ color: "var(--text-secondary)" }}>
                        {rec.text}
                      </p>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          setExportedPreviewUrl(url);
                          setExportedPlayNonce((n) => n + 1);
                          void notify(notificationsEnabled, t("toast.title"), t("toast.playing"));
                        }}
                        className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs hover:border-cyan-400/50"
                        style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                      >
                        <Play className="w-3 h-3" />
                        {t("synthesize.play")}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSaveAs(rec)}
                        className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs hover:border-emerald-400/50"
                        style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                      >
                        <Save className="w-3 h-3" />
                        {t("synthesize.saveAs")}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReveal(rec)}
                        className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs hover:border-purple-400/50"
                        style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                      >
                        <FolderOpen className="w-3 h-3" />
                        {t("synthesize.reveal")}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(rec)}
                        title={t("synthesize.delete")}
                        className="p-1.5 rounded-xl border hover:border-rose-500/50 text-rose-300"
                        style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </GlassCard>
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-2.5">
      <GlassCard className="flex-1 min-h-0 p-4 flex flex-col gap-2.5">
        <div className="flex flex-wrap items-center justify-end gap-2 shrink-0">
          <div className="flex flex-wrap items-center gap-2">
            {/* Unified Glass Dropdown: Local + Externo */}
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                title={selectorLabel}
                className="w-[225px] inline-flex items-center justify-between gap-1.5 rounded-xl px-2.5 py-1.5 text-xs font-mono border transition-colors hover:brightness-110"
                style={{
                  backgroundColor: "var(--bg-input)",
                  borderColor: isEndpointMode
                    ? "rgba(16,185,129,0.45)"
                    : "var(--border-glass)",
                  color: isEndpointMode ? "#34d399" : "var(--text-primary)",
                }}
              >
                <span className="truncate">{selectorLabel}</span>
                <ChevronDown
                  className={clsx("w-3.5 h-3.5 shrink-0 transition-transform", menuOpen && "rotate-180")}
                />
              </button>

              {menuOpen &&
                menuPos &&
                createPortal(
                  <div
                    ref={dropdownRef}
                    className="fixed z-[9999] max-h-[320px] overflow-y-auto rounded-2xl border p-1.5 shadow-2xl backdrop-blur-xl flex flex-col gap-0.5"
                    style={{
                      top: menuPos.top,
                      left: menuPos.left,
                      width: menuPos.width,
                      backgroundColor: "var(--bg-elevated)",
                      borderColor: "var(--border-glass)",
                    }}
                  >
                  <span
                    className="px-2.5 pt-1 pb-0.5 text-[10px] font-mono uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {t("models.local")}
                  </span>

                  {localOptions.length > 0 ? (
                    localOptions.map((m) => {
                      const active = !isEndpointMode && m.id === activeLocal?.id;
                      return (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => selectLocalModel(m.id)}
                          className={clsx(
                            "w-full text-left rounded-xl px-2.5 py-1.5 text-xs flex items-center justify-between gap-2 hover:bg-white/10",
                            active && "bg-purple-500/15 text-purple-200"
                          )}
                        >
                          <div className="min-w-0">
                            <div className="font-medium truncate">{m.name}</div>
                            <div className="text-[10px] font-mono opacity-65 truncate">
                              {m.subtitle}
                            </div>
                          </div>
                          {active && <Check className="w-3.5 h-3.5 shrink-0 text-purple-400" />}
                        </button>
                      );
                    })
                  ) : (
                    <div
                      className="px-2.5 py-1.5 text-[11px]"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {t("models.noLocalInstalled")}
                    </div>
                  )}

                  <div className="my-1 h-px bg-white/10" />

                  <span
                    className="px-2.5 pt-0.5 pb-0.5 text-[10px] font-mono uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {t("models.externalGroup")}
                  </span>

                  {ttsEndpoints.length > 0 ? (
                    ttsEndpoints.map((ep) => {
                      const active = isEndpointMode && ep.id === settings.active_tts_endpoint_id;
                      return (
                        <button
                          key={ep.id}
                          type="button"
                          onClick={() => selectEndpoint(ep.id)}
                          className={clsx(
                            "w-full text-left rounded-xl px-2.5 py-1.5 text-xs flex items-center justify-between gap-2 hover:bg-white/10",
                            active && "bg-emerald-500/15 text-emerald-300"
                          )}
                        >
                          <div className="min-w-0">
                            <div className="font-medium truncate">{ep.name}</div>
                            <div className="text-[10px] font-mono opacity-70 truncate">
                              {endpointProviderSubtitle(ep)}
                            </div>
                          </div>
                          {active && <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" />}
                        </button>
                      );
                    })
                  ) : (
                      <div
                        className="px-2.5 py-1.5 text-[11px]"
                        style={{ color: "var(--text-secondary)" }}
                      >
                        {t("models.noExternalConfigured")}
                      </div>
                    )}
                  </div>,
                  document.body
                )}
            </div>

            {isEndpointMode ? (
              activeEp && (
                <span
                  className="rounded-xl border px-2.5 py-1.5 text-xs font-mono"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {activeEp.voice || activeEp.model || t("synthesize.endpointActive")}
                </span>
              )
            ) : usesCloneProfiles ? (
              <div className="flex items-center gap-1.5">
                <select
                  value={selectedProfile?.id || ""}
                  onChange={(e) => onSelectProfileId(e.target.value)}
                  className="rounded-xl border px-2.5 py-1.5 text-xs font-medium outline-none"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                    color: "var(--text-primary)",
                  }}
                >
                  {visibleProfiles.length === 0 ? (
                    <option value="">{t("synthesize.noProfiles")}</option>
                  ) : (
                    visibleProfiles.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} ({p.engine})
                      </option>
                    ))
                  )}
                </select>
                {visibleProfiles.length === 0 && onOpenProfiles && (
                  <button
                    type="button"
                    onClick={onOpenProfiles}
                    className="rounded-xl border px-2.5 py-1.5 text-xs font-medium hover:bg-white/10"
                    style={{
                      borderColor: "var(--border-glass)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {t("synthesize.createProfileCta")}
                  </button>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <select
                  value={selectedBuiltinVoice}
                  onChange={(e) => setSelectedBuiltinVoice(e.target.value)}
                  className="rounded-xl border px-2.5 py-1.5 text-xs font-medium outline-none"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                    color: "var(--text-primary)",
                  }}
                >
                  <option value="">{t("synthesize.builtinVoices")} (Auto)</option>
                  {builtinVoices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.label}
                    </option>
                  ))}
                </select>
                {(!activeLocal?.runtime_supported || availableLanguages.length === 0) &&
                  onOpenModels && (
                    <button
                      type="button"
                      onClick={onOpenModels}
                      className="rounded-xl border px-2.5 py-1.5 text-xs font-medium hover:bg-white/10"
                      style={{
                        borderColor: "var(--border-glass)",
                        color: "var(--text-primary)",
                      }}
                    >
                      {t("synthesize.installInModels")}
                    </button>
                  )}
              </div>
            )}

            <div className="relative" ref={langMenuRef}>
              <button
                type="button"
                onClick={() => setLangMenuOpen((o) => !o)}
                disabled={availableLanguages.length === 0 && !isEndpointMode}
                className="rounded-xl border px-2.5 py-1.5 text-xs outline-none flex items-center gap-1.5 min-w-[7rem]"
                style={{
                  backgroundColor: "var(--bg-input)",
                  borderColor: "var(--border-glass)",
                  color: "var(--text-primary)",
                }}
              >
                <span className="truncate">
                  {availableLanguages.length === 0 && !isEndpointMode
                    ? t("synthesize.noLanguagesReady")
                    : language}
                </span>
                <ChevronDown className="w-3.5 h-3.5 opacity-60 shrink-0" />
              </button>
              {langMenuOpen &&
                langMenuPos &&
                createPortal(
                  <div
                    ref={langDropdownRef}
                    className="fixed z-[9999] max-h-56 overflow-y-auto rounded-xl border p-1 shadow-2xl backdrop-blur-xl"
                    style={{
                      top: langMenuPos.top,
                      left: langMenuPos.left,
                      width: langMenuPos.width,
                      backgroundColor: "var(--bg-elevated)",
                      borderColor: "var(--border-glass)",
                    }}
                  >
                  {(isEndpointMode ? FALLBACK_LANGUAGES : availableLanguages).map((l) => {
                    const code = LABEL_TO_CODE[l] || l.toLowerCase().slice(0, 2);
                    return (
                      <div
                        key={l}
                        className={clsx(
                          "flex items-center gap-1 rounded-lg px-1.5 py-1 text-xs",
                          language === l && "bg-white/10",
                        )}
                      >
                        <button
                          type="button"
                          className="flex-1 text-left px-1 py-0.5 truncate hover:opacity-90"
                          style={{ color: "var(--text-primary)" }}
                          onClick={() => {
                            setLanguage(l);
                            setLangMenuOpen(false);
                          }}
                        >
                          {l}
                        </button>
                        {showLangTrash && (
                          <button
                            type="button"
                            title={t("synthesize.removeLanguage")}
                            disabled={langBusy}
                            className="p-1 rounded-md text-rose-300/80 hover:bg-rose-500/15 hover:text-rose-200 disabled:opacity-40"
                            onClick={(e) => {
                              e.stopPropagation();
                              void removeReadyLanguage(code);
                            }}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    );
                  })}
                  {!isEndpointMode &&
                    availableLanguages.length === 0 &&
                    onOpenModels && (
                      <button
                        type="button"
                        className="w-full text-left rounded-lg px-2.5 py-1.5 text-xs hover:bg-white/10"
                        style={{ color: "var(--text-primary)" }}
                        onClick={() => {
                          setLangMenuOpen(false);
                          onOpenModels();
                        }}
                      >
                        {t("synthesize.installInModels")}
                      </button>
                    )}
                  </div>,
                  document.body
                )}
            </div>
          </div>
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("synthesize.inputPlaceholder")}
          className="flex-1 min-h-[120px] w-full rounded-2xl border p-3.5 text-sm outline-none resize-none"
          style={{
            backgroundColor: "var(--bg-input)",
            borderColor: "var(--border-glass)",
            color: "var(--text-primary)",
          }}
        />

        {pendingForceMode && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-xs shrink-0">
            <div className="flex items-center gap-2 text-amber-200">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{t("synthesize.confirmCaptions")}</span>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => runSynth(pendingForceMode, true)}
                className="rounded-lg px-2.5 py-1 bg-amber-500/25 border border-amber-400/50 font-medium"
              >
                {t("synthesize.stopCaptionsAndRun")}
              </button>
              <button
                type="button"
                onClick={() => setPendingForceMode(null)}
                className="rounded-lg px-2.5 py-1 border border-white/15"
              >
                {t("synthesize.cancel")}
              </button>
            </div>
          </div>
        )}

        {usesCloneProfiles && !selectedProfile && text.trim() && (
          <div className="shrink-0 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200 flex items-center justify-between gap-2">
            <span>{t("synthesize.profileRequiredHint")}</span>
            {onOpenProfiles && (
              <button
                type="button"
                onClick={onOpenProfiles}
                className="shrink-0 rounded-lg border border-amber-400/40 px-2.5 py-1 text-[11px] font-medium hover:bg-amber-500/20"
              >
                {t("synthesize.createProfileCta")}
              </button>
            )}
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300 shrink-0">
            {error}
          </div>
        )}

        {/* Single shared status/player slot: shows loading bar until first audio chunk is ready, then swaps in ChunkedAudioPlayer */}
        {(() => {
          const hasReadyChunk = playChunks.some((c) => Boolean(c.audioUrl));
          if (busyMode && !hasReadyChunk) {
            return (
              <div className="flex flex-col gap-1 shrink-0 py-1">
                <div className="h-1.5 w-full rounded-full overflow-hidden bg-white/10">
                  <div className="h-full w-2/3 rounded-full bg-gradient-to-r from-purple-500 via-cyan-400 to-purple-500 animate-pulse" />
                </div>
                <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {t("synthesize.generating")}
                </span>
              </div>
            );
          }
          if (playChunks.length > 0 && hasReadyChunk) {
            return (
              <ChunkedAudioPlayer
                ref={playerRef}
                chunks={playChunks}
                isGenerating={isGeneratingSession}
                autoPlayNonce={autoPlayNonce}
                onPlaybackChange={onPlaybackStateChange}
              />
            );
          }
          return null;
        })()}

        <div className="flex flex-wrap items-center justify-between gap-3 shrink-0 pt-0.5">
          <div className="flex items-center gap-2">
            {busyMode === "play" || isGeneratingSession ? (
              <BorderBeamButton
                variant="rose"
                onClick={() => {
                  synthTokenRef.current++;
                  prefetchAbortRef.current?.abort();
                  playerRef.current?.pause();
                  setBusyMode(null);
                  setIsGeneratingSession(false);
                  if (baseUrl) void cancelTtsSynthesis(baseUrl);
                }}
              >
                <Loader2 className="w-4 h-4 animate-spin" />
                {t("synthesize.stop")}
              </BorderBeamButton>
            ) : (
              <BorderBeamButton
                disabled={!canSynthesize}
                onClick={() => runSynth("play")}
              >
                <Play className="w-4 h-4" />
                {t("synthesize.play")}
              </BorderBeamButton>
            )}

            <BorderBeamButton
              variant="emerald"
              disabled={!canSynthesize}
              onClick={() => runSynth("wav")}
            >
              {busyMode === "wav" ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              {t("synthesize.save")}
            </BorderBeamButton>
          </div>

          <button
            type="button"
            disabled={(!text.length && playChunks.length === 0) || !!busyMode}
            onClick={() => {
              synthTokenRef.current++;
              prefetchAbortRef.current?.abort();
              playerRef.current?.pause();
              setText("");
              setPlayChunks([]);
              setIsGeneratingSession(false);
              setLastStats(null);
              sessionIdRef.current = null;
              sessionSigRef.current = "";
              if (baseUrl) void clearPlaySession(baseUrl);
            }}
            className="ml-auto mr-2 inline-flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-40 hover:border-rose-400/50"
            style={{
              backgroundColor: "var(--bg-surface-strong)",
              borderColor: "var(--border-glass)",
              color: "var(--text-secondary)",
            }}
          >
            <Eraser className="w-4 h-4" />
            {t("synthesize.erase")}
          </button>

          {lastStats && (
            <div className="text-[11px] font-mono" style={{ color: "var(--text-secondary)" }}>
              {lastStats.dur.toFixed(2)}s · {lastStats.elapsed.toFixed(2)}s · RTF {lastStats.rtf.toFixed(3)}
            </div>
          )}
        </div>
      </GlassCard>

      <button
        type="button"
        onClick={() => setSubView("exported")}
        className="w-full text-left group shrink-0"
      >
        <GlassCard className="px-4 py-2.5 flex items-center justify-between gap-3 group-hover:border-cyan-400/50">
          <div className="flex items-center gap-2.5">
            <FolderArchive className="w-4 h-4 text-cyan-400 shrink-0" />
            <span className="text-sm font-medium">{t("synthesize.openExported")}</span>
            <span
              className="rounded-full px-2 py-0.5 text-[11px] font-mono border"
              style={{
                borderColor: "var(--border-glass)",
                backgroundColor: "var(--bg-elevated)",
                color: "var(--text-secondary)",
              }}
            >
              {history.length}
            </span>
          </div>
          <ChevronRight
            className="w-4 h-4 transition-transform group-hover:translate-x-0.5"
            style={{ color: "var(--text-secondary)" }}
          />
        </GlassCard>
      </button>
    </div>
  );
};
