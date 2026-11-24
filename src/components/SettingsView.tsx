import React, { useState } from "react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import {
  Bell,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Eye,
  EyeOff,
  FolderOpen,
  Globe,
  KeyRound,
  Keyboard,
  Palette,
  Plus,
  Server,
  Terminal,
  Trash2,
  Zap,
} from "lucide-react";
import { clsx } from "clsx";
import { AVAILABLE_LANGUAGES, useI18n, type LanguageCode } from "../i18n";
import { isTauri, sendWindowsToast, setReadHotkey, testExternalEndpoint } from "../services/api";
import type {
  AccentPreset,
  AppSettings,
  EndpointProtocol,
  EndpointTestResponse,
  ExternalEndpointConfig,
} from "../types";
import {
  createEndpointFromPreset,
  ENDPOINT_PRESETS,
  type EndpointPresetTemplate,
  reconcileActiveEndpointId,
} from "../utils/endpointPresets";
import { BorderBeamButton } from "./BorderBeamButton";
import { GlassCard } from "./GlassCard";

interface SettingsViewProps {
  settings: AppSettings;
  resolvedModelsDir: string;
  resolvedOutputsDir: string;
  apiBaseUrl: string;
  apiRunning: boolean;
  apiPort: number;
  onSave: (next: AppSettings) => Promise<void>;
}

const ACCENTS: { id: AccentPreset; color: string; label: string }[] = [
  { id: "cyber", color: "#a855f7", label: "Cyber" },
  { id: "emerald", color: "#10b981", label: "Emerald" },
  { id: "amber", color: "#f59e0b", label: "Amber" },
  { id: "rose", color: "#f43f5e", label: "Rose" },
];

// Physical key, not the character the layout prints. `KeyboardEvent.code`
// matches the names global-hotkey already parses (KeyM, Digit7, Slash, NumpadDivide).
function acceleratorFromEvent(ev: KeyboardEvent): string | null {
  if (ev.repeat || !ev.code || ev.code === "Unidentified") return null;
  if (/^(Control|Shift|Alt|Meta)(Left|Right)$/.test(ev.code)) return null;
  const mods: string[] = [];
  if (ev.ctrlKey) mods.push("Ctrl");
  if (ev.altKey) mods.push("Alt");
  if (ev.shiftKey) mods.push("Shift");
  if (ev.metaKey) mods.push("Super");
  if (mods.length === 0) return null;
  return [...mods, ev.code].join("+");
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  settings,
  resolvedModelsDir,
  resolvedOutputsDir,
  apiBaseUrl,
  apiRunning,
  apiPort,
  onSave,
}) => {
  const { t } = useI18n();
  const [draft, setDraft] = useState<AppSettings>(settings);
  const [savedFlag, setSavedFlag] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [showLocalKey, setShowLocalKey] = useState(false);

  // External API tabbed accordion state
  const [activeEpTab, setActiveEpTab] = useState<"tts" | "stt">("tts");
  const [expandedEpId, setExpandedEpId] = useState<string | null>(null);
  const [showExtKeys, setShowExtKeys] = useState<Record<string, boolean>>({});
  const [epTests, setEpTests] = useState<Record<string, EndpointTestResponse>>({});
  const [testingEpId, setTestingEpId] = useState<string | null>(null);

  React.useEffect(() => {
    setDraft(settings);
  }, [settings]);

  const [recordingHotkey, setRecordingHotkey] = useState(false);
  const [hotkeyError, setHotkeyError] = useState<string | null>(null);

  const applyHotkey = async (accel: string) => {
    try {
      await setReadHotkey(accel);
      setHotkeyError(null);
      await commit({ ...draft, read_hotkey: accel });
    } catch (err) {
      setHotkeyError(err instanceof Error ? err.message : String(err));
    }
  };

  const clearHotkey = () => applyHotkey("");

  React.useEffect(() => {
    if (!recordingHotkey) return;
    const onKeyDown = (ev: KeyboardEvent) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (
        ev.code === "Escape" &&
        !ev.ctrlKey &&
        !ev.altKey &&
        !ev.shiftKey &&
        !ev.metaKey
      ) {
        setRecordingHotkey(false);
        return;
      }
      const accel = acceleratorFromEvent(ev);
      if (!accel) return;
      setRecordingHotkey(false);
      void applyHotkey(accel);
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordingHotkey, draft]);

  const commit = async (next: AppSettings) => {
    setDraft(next);
    await onSave(next);
    setSavedFlag(true);
    setTimeout(() => setSavedFlag(false), 1800);
  };

  const pickFolder = async (field: "models_dir" | "outputs_dir") => {
    if (!isTauri()) return;
    const selected = await openDialog({ directory: true, multiple: false });
    if (typeof selected === "string" && selected.length > 0) {
      await commit({ ...draft, [field]: selected });
    }
  };

  const copyText = async (txt: string, key = txt) => {
    await navigator.clipboard.writeText(txt);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1500);
  };

  const generateLocalBearer = async () => {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    await commit({ ...draft, api_bearer_token: `sk-speech-${hex}` });
  };

  const updateEndpoint = (id: string, patch: Partial<ExternalEndpointConfig>) => {
    const nextList = draft.external_endpoints.map((ep) =>
      ep.id === id ? { ...ep, ...patch } : ep
    );
    setDraft({ ...draft, external_endpoints: nextList });
  };

  const addNewEndpoint = (kind: "tts" | "stt", preset?: EndpointPresetTemplate) => {
    const fresh = createEndpointFromPreset(kind, preset);
    if (!preset) fresh.name = "";
    const nextList = [...draft.external_endpoints, fresh];
    const nextSettings: AppSettings = {
      ...draft,
      external_endpoints: nextList,
      active_tts_endpoint_id:
        kind === "tts" && !draft.active_tts_endpoint_id
          ? fresh.id
          : draft.active_tts_endpoint_id,
      active_stt_endpoint_id:
        kind === "stt" && !draft.active_stt_endpoint_id
          ? fresh.id
          : draft.active_stt_endpoint_id,
    };
    setDraft(nextSettings);
    setExpandedEpId(fresh.id);
    if (preset) {
      commit(nextSettings);
    }
  };

  const handleTestEp = async (ep: ExternalEndpointConfig) => {
    setTestingEpId(ep.id);
    try {
      await commit(draft);
      const res = await testExternalEndpoint(apiBaseUrl, ep.id);
      setEpTests((prev) => ({ ...prev, [ep.id]: res }));
    } finally {
      setTestingEpId(null);
    }
  };

  const handleDeleteEp = async (ep: ExternalEndpointConfig) => {
    const nextList = draft.external_endpoints.filter((x) => x.id !== ep.id);
    const nextSettings: AppSettings = {
      ...draft,
      external_endpoints: nextList,
      active_tts_endpoint_id: reconcileActiveEndpointId(
        nextList,
        "tts",
        draft.active_tts_endpoint_id
      ),
      active_stt_endpoint_id: reconcileActiveEndpointId(
        nextList,
        "stt",
        draft.active_stt_endpoint_id
      ),
    };
    if (expandedEpId === ep.id) setExpandedEpId(null);
    await commit(nextSettings);
  };

  const handleSetActiveEp = async (ep: ExternalEndpointConfig) => {
    const patch =
      ep.kind === "tts"
        ? { active_tts_endpoint_id: ep.id }
        : { active_stt_endpoint_id: ep.id };
    await commit({ ...draft, ...patch });
  };

  const ttsUrl = `${apiBaseUrl}/v1/audio/speech`;
  const sttUrl = `${apiBaseUrl}/v1/audio/transcriptions`;
  const serveOn = draft.api_endpoint_enabled;

  const sampleCurl = [
    `curl -X POST "${ttsUrl}"`,
    ...(draft.api_bearer_token.trim()
      ? [`-H "Authorization: Bearer ${draft.api_bearer_token.trim()}"`]
      : []),
    `-H "Content-Type: application/json"`,
    `-d '{"model":"qwen3-1.7b","voice":"mario","input":"Hola mundo"}'`,
    `--output speech.wav`,
  ].join(" ");

  const ttsEndpoints = draft.external_endpoints.filter((e) => e.kind === "tts");
  const sttEndpoints = draft.external_endpoints.filter((e) => e.kind === "stt");
  const visibleEndpoints = activeEpTab === "tts" ? ttsEndpoints : sttEndpoints;

  return (
    <div className="flex flex-col gap-3.5 pb-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">{t("settings.title")}</h1>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {t("settings.subtitle")}
          </p>
        </div>
        {savedFlag && (
          <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
            <Check className="w-3.5 h-3.5" />
            {t("settings.saved")}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        <GlassCard className="p-4 flex flex-col gap-3.5">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Globe className="w-4 h-4 text-cyan-400" />
            <span>{t("settings.language")}</span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <label className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("settings.language")}
            </label>
            <select
              value={draft.language}
              onChange={(e) => commit({ ...draft, language: e.target.value as LanguageCode })}
              className="rounded-xl border px-3 py-1.5 text-xs outline-none"
              style={{
                backgroundColor: "var(--bg-input)",
                borderColor: "var(--border-glass)",
                color: "var(--text-primary)",
              }}
            >
              {AVAILABLE_LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>

          <div className="h-px bg-white/10" />

          <div className="flex items-center gap-2 text-sm font-semibold">
            <Palette className="w-4 h-4 text-purple-400" />
            <span>{t("settings.appearance")}</span>
          </div>

          <div className="flex items-center justify-between gap-3">
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("settings.theme")}
            </span>
            <div className="flex gap-2">
              {(["dark", "light"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => commit({ ...draft, theme: m })}
                  className={clsx(
                    "rounded-xl px-3 py-1 text-xs font-medium border transition-all",
                    draft.theme === m ? "border-purple-400 bg-purple-500/20" : "border-white/10 opacity-70"
                  )}
                >
                  {t(`settings.${m}`)}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between gap-3">
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("settings.accent")}
            </span>
            <div className="flex gap-2">
              {ACCENTS.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => commit({ ...draft, accent: a.id })}
                  title={a.label}
                  className={clsx(
                    "w-6 h-6 rounded-full border-2 transition-transform",
                    draft.accent === a.id ? "scale-110 border-white" : "border-transparent opacity-70"
                  )}
                  style={{ backgroundColor: a.color }}
                />
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between gap-3">
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("settings.asciiFx")}
            </span>
            <input
              type="checkbox"
              checked={draft.ascii_fx_enabled}
              onChange={(e) => commit({ ...draft, ascii_fx_enabled: e.target.checked })}
              className="w-4 h-4 accent-purple-500"
            />
          </div>

          <div className="flex items-center justify-between gap-3">
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("settings.asciiOpacity")} ({Math.round(draft.ascii_fx_opacity * 100)}%)
            </span>
            <input
              type="range"
              min={0.04}
              max={0.22}
              step={0.01}
              value={draft.ascii_fx_opacity}
              onChange={(e) => setDraft({ ...draft, ascii_fx_opacity: parseFloat(e.target.value) })}
              onMouseUp={() => commit(draft)}
              onTouchEnd={() => commit(draft)}
              className="w-36 accent-cyan-400"
            />
          </div>
        </GlassCard>

        <GlassCard className="p-4 flex flex-col gap-3.5">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <FolderOpen className="w-4 h-4 text-cyan-400" />
            <span>{t("settings.paths")}</span>
          </div>

          {([
            { key: "models_dir", label: t("settings.modelsDir"), resolved: resolvedModelsDir },
            { key: "outputs_dir", label: t("settings.outputsDir"), resolved: resolvedOutputsDir },
          ] as const).map((row) => (
            <div key={row.key} className="flex flex-col gap-1">
              <span className="text-xs font-medium">{row.label}</span>
              <div className="flex items-center gap-1.5">
                <input
                  readOnly
                  value={draft[row.key] || t("settings.defaultPath")}
                  className="flex-1 rounded-xl border px-2.5 py-1.5 text-xs font-mono outline-none"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                    color: "var(--text-primary)",
                  }}
                />
                <button
                  type="button"
                  onClick={() => pickFolder(row.key)}
                  className="rounded-xl border px-2.5 py-1.5 text-xs font-medium hover:border-cyan-400/50"
                  style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                >
                  {t("settings.selectPath")}
                </button>
                <button
                  type="button"
                  onClick={() => commit({ ...draft, [row.key]: "" })}
                  className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1.5 text-xs font-medium hover:border-rose-400/50"
                  style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                >
                  <Trash2 className="w-3 h-3" />
                  {t("settings.clear")}
                </button>
              </div>
              <span className="text-[10px] font-mono truncate" style={{ color: "var(--text-muted)" }}>
                {t("settings.resolved")}: {row.resolved}
              </span>
            </div>
          ))}

          <div className="h-px bg-white/10" />

          <div className="flex items-center gap-2 text-sm font-semibold">
            <Bell className="w-4 h-4 text-purple-400" />
            <span>{t("settings.subtitlesSection")}</span>
          </div>

          <div className="flex items-center justify-between gap-3">
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("settings.maxHistory")}
            </span>
            <input
              type="number"
              min={5}
              max={200}
              value={draft.captions_max_history}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  captions_max_history: Math.max(5, Math.min(200, Number(e.target.value) || 20)),
                })
              }
              onBlur={() => commit(draft)}
              className="w-20 rounded-xl border px-2.5 py-1 text-xs font-mono text-right outline-none"
              style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
            />
          </div>

          <div className="flex items-center justify-between gap-3">
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("settings.notifications")}
            </span>
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() =>
                  sendWindowsToast("Speech Studio", "Windows Toast Notifications active!", 100)
                }
                className="rounded-xl border px-2.5 py-1 text-xs font-medium hover:border-purple-400/50"
                style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
              >
                {t("settings.testToast")}
              </button>
              <input
                type="checkbox"
                checked={draft.notifications_enabled}
                onChange={(e) => commit({ ...draft, notifications_enabled: e.target.checked })}
                className="w-4 h-4 accent-purple-500"
              />
            </div>
          </div>

          <div className="h-px bg-white/10" />

          <div className="flex items-center gap-2 text-sm font-semibold">
            <Keyboard className="w-4 h-4 text-cyan-400" />
            <span>{t("settings.hotkeySection")}</span>
          </div>
          <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            {t("settings.hotkeyHint")}
          </span>
          <div className="flex items-center justify-between gap-2">
            <div
              className={clsx(
                "flex-1 rounded-xl border px-3 py-1.5 text-xs font-mono",
                recordingHotkey && "border-cyan-400/70 animate-pulse"
              )}
              style={{
                backgroundColor: "var(--bg-input)",
                borderColor: recordingHotkey ? undefined : "var(--border-glass)",
                color: draft.read_hotkey ? "var(--text-primary)" : "var(--text-muted)",
              }}
            >
              {recordingHotkey
                ? t("settings.hotkeyPressNow")
                : draft.read_hotkey
                  ? draft.read_hotkey
                  : t("settings.hotkeyUnassigned")}
            </div>
            <button
              type="button"
              onClick={() => {
                setHotkeyError(null);
                setRecordingHotkey((v) => !v);
              }}
              className="rounded-xl border px-3 py-1.5 text-xs font-medium hover:border-cyan-400/50"
              style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
            >
              {recordingHotkey ? t("models.cancel") : t("settings.hotkeyRecord")}
            </button>
            <button
              type="button"
              disabled={!draft.read_hotkey}
              onClick={clearHotkey}
              className="inline-flex items-center gap-1 rounded-xl border px-3 py-1.5 text-xs font-medium disabled:opacity-40 hover:border-rose-400/50"
              style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
            >
              <Trash2 className="w-3 h-3" />
              {t("settings.clear")}
            </button>
          </div>
          {hotkeyError && (
            <span className="text-[11px] text-rose-300">
              {t("settings.hotkeyError")}: {hotkeyError}
            </span>
          )}
        </GlassCard>

        {/* SERVE LOCAL API ENDPOINT (Collapses when OFF) */}
        <GlassCard className="p-4 flex flex-col gap-3.5 lg:col-span-2">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold">
              <Server className={clsx("w-4 h-4", serveOn ? "text-emerald-400" : "text-rose-400")} />
              <span>{t("settings.apiSection")}</span>
              <span
                className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-mono"
                style={{
                  borderColor:
                    apiRunning && serveOn
                      ? "rgba(16, 185, 129, 0.4)"
                      : "rgba(244, 63, 94, 0.4)",
                }}
              >
                <span
                  className={clsx(
                    "h-2 w-2 rounded-full",
                    apiRunning && serveOn
                      ? "bg-emerald-400 shadow-[0_0_8px_#34d399]"
                      : "bg-rose-500"
                  )}
                />
                {serveOn ? `${t("topbar.apiOnline")} · :${apiPort}` : t("topbar.apiOffline")}
              </span>
            </div>

            <button
              type="button"
              onClick={() => commit({ ...draft, api_endpoint_enabled: !serveOn })}
              className="relative flex items-center w-[94px] h-7 rounded-full p-0.5 border transition-colors"
              style={{
                backgroundColor: "var(--bg-input)",
                borderColor: serveOn ? "rgba(16, 185, 129, 0.5)" : "rgba(244, 63, 94, 0.45)",
              }}
            >
              <span
                className={clsx(
                  "absolute top-0.5 bottom-0.5 w-[44px] rounded-full transition-transform duration-200",
                  serveOn
                    ? "translate-x-0 bg-emerald-500/25 border border-emerald-400/60"
                    : "translate-x-[44px] bg-rose-500/25 border border-rose-400/60"
                )}
              />
              <span
                className={clsx(
                  "relative z-10 w-1/2 text-center font-mono text-[11px] font-semibold",
                  serveOn ? "text-emerald-300" : "opacity-55"
                )}
              >
                ON
              </span>
              <span
                className={clsx(
                  "relative z-10 w-1/2 text-center font-mono text-[11px] font-semibold",
                  !serveOn ? "text-rose-300" : "opacity-55"
                )}
              >
                OFF
              </span>
            </button>
          </div>

          {serveOn && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                    {t("settings.apiHost")}
                  </label>
                  <select
                    value={draft.api_bind_host}
                    onChange={(e) =>
                      commit({
                        ...draft,
                        api_bind_host: e.target.value as "127.0.0.1" | "0.0.0.0",
                      })
                    }
                    className="rounded-xl border px-2.5 py-1.5 text-xs font-mono outline-none"
                    style={{
                      backgroundColor: "var(--bg-input)",
                      borderColor: "var(--border-glass)",
                      color: "var(--text-primary)",
                    }}
                  >
                    <option value="127.0.0.1">{t("settings.apiLocalhost")}</option>
                    <option value="0.0.0.0">{t("settings.apiLan")}</option>
                  </select>
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                    {t("settings.apiPort")}
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      min={0}
                      max={65535}
                      value={draft.api_fixed_port}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          api_fixed_port: Math.max(0, Math.min(65535, Number(e.target.value) || 0)),
                        })
                      }
                      className="w-28 rounded-xl border px-2.5 py-1.5 text-xs font-mono outline-none"
                      style={{
                        backgroundColor: "var(--bg-input)",
                        borderColor: "var(--border-glass)",
                      }}
                    />
                    <BorderBeamButton onClick={() => commit(draft)} activeBeam={false}>
                      {t("settings.save")}
                    </BorderBeamButton>
                  </div>
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                    {t("settings.apiBearer")}
                  </label>
                  <div className="flex items-center gap-1.5">
                    <input
                      type={showLocalKey ? "text" : "password"}
                      value={draft.api_bearer_token}
                      onChange={(e) => setDraft({ ...draft, api_bearer_token: e.target.value })}
                      onBlur={() => commit(draft)}
                      placeholder={t("settings.apiBearerPlaceholder")}
                      className="flex-1 min-w-0 rounded-xl border px-2.5 py-1.5 text-xs font-mono outline-none"
                      style={{
                        backgroundColor: "var(--bg-input)",
                        borderColor: "var(--border-glass)",
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowLocalKey((v) => !v)}
                      className="p-1.5 rounded-xl border hover:border-purple-400/50"
                      style={{
                        borderColor: "var(--border-glass)",
                        backgroundColor: "var(--bg-elevated)",
                      }}
                    >
                      {showLocalKey ? (
                        <EyeOff className="w-3.5 h-3.5" />
                      ) : (
                        <Eye className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={generateLocalBearer}
                      className="inline-flex items-center gap-1 rounded-xl border px-2 py-1.5 text-xs hover:border-cyan-400/50"
                      style={{
                        borderColor: "var(--border-glass)",
                        backgroundColor: "var(--bg-elevated)",
                      }}
                    >
                      <KeyRound className="w-3 h-3" />
                      {t("settings.generateKey")}
                    </button>
                    {draft.api_bearer_token && (
                      <button
                        type="button"
                        onClick={() => copyText(draft.api_bearer_token)}
                        className="p-1.5 rounded-xl border hover:border-emerald-400/50"
                        style={{
                          borderColor: "var(--border-glass)",
                          backgroundColor: "var(--bg-elevated)",
                        }}
                      >
                        {copiedKey === draft.api_bearer_token ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                    )}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {([
                  { label: t("settings.apiTtsUrl"), url: ttsUrl },
                  { label: t("settings.apiSttUrl"), url: sttUrl },
                ] as const).map((item) => (
                  <div key={item.url} className="flex flex-col gap-1">
                    <span className="text-[11px] font-medium" style={{ color: "var(--text-secondary)" }}>
                      {item.label}
                    </span>
                    <div
                      className="flex items-center justify-between gap-2 rounded-xl border px-2.5 py-1.5 text-xs font-mono"
                      style={{
                        backgroundColor: "var(--bg-input)",
                        borderColor: "var(--border-glass)",
                      }}
                    >
                      <span className="truncate">{item.url}</span>
                      <button
                        type="button"
                        onClick={() => copyText(item.url)}
                        className="shrink-0 p-1 rounded hover:bg-white/10"
                      >
                        {copiedKey === item.url ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                  {t("settings.apiPortHint")}
                </span>
                <button
                  type="button"
                  onClick={() => copyText(sampleCurl, "__curl__")}
                  className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium hover:border-emerald-400/50"
                  style={{
                    borderColor: "var(--border-glass)",
                    backgroundColor: "var(--bg-elevated)",
                  }}
                >
                  {copiedKey === "__curl__" ? (
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                  ) : (
                    <Terminal className="w-3.5 h-3.5 text-emerald-300" />
                  )}
                  {copiedKey === "__curl__" ? t("transcriber.copied") : t("settings.copyCurl")}
                </button>
              </div>
            </>
          )}
        </GlassCard>

        {/* EXTERNAL API CONNECTIONS (Single card, 2 big tabs TTS | STT + collapsible accordion) */}
        <GlassCard className="p-4 flex flex-col gap-3.5 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Globe className="w-4 h-4 text-cyan-400" />
              <span>{t("settings.externalSection")}</span>
            </div>

            <div className="flex items-center gap-2">
              <div
                className="inline-flex rounded-full p-0.5 border"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-input)",
                }}
              >
                <button
                  type="button"
                  onClick={() => {
                    setActiveEpTab("tts");
                    setExpandedEpId(null);
                  }}
                  className={clsx(
                    "px-4 py-1 rounded-full text-xs font-semibold transition-colors",
                    activeEpTab === "tts"
                      ? "bg-purple-500/25 text-purple-200 border border-purple-400/60"
                      : "opacity-65 hover:opacity-100"
                  )}
                >
                  TTS ({ttsEndpoints.length})
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActiveEpTab("stt");
                    setExpandedEpId(null);
                  }}
                  className={clsx(
                    "px-4 py-1 rounded-full text-xs font-semibold transition-colors",
                    activeEpTab === "stt"
                      ? "bg-cyan-500/25 text-cyan-200 border border-cyan-400/60"
                      : "opacity-65 hover:opacity-100"
                  )}
                >
                  STT ({sttEndpoints.length})
                </button>
              </div>

              <button
                type="button"
                onClick={() => addNewEndpoint(activeEpTab)}
                className="inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium hover:border-cyan-400/60 text-cyan-300"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-elevated)",
                }}
              >
                <Plus className="w-3.5 h-3.5" />
                {t("settings.newProfile")}
              </button>
            </div>
          </div>

          {visibleEndpoints.length === 0 ? (
            <div
              className="rounded-2xl border border-dashed p-4 flex flex-col items-center gap-3 text-center"
              style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-input)" }}
            >
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                {t("settings.emptyEndpoints")}
              </span>
              <div className="flex flex-wrap justify-center gap-1.5">
                {ENDPOINT_PRESETS[activeEpTab].map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => addNewEndpoint(activeEpTab, p)}
                    className="inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs hover:border-cyan-400/60"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    <Plus className="w-3 h-3" />
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {visibleEndpoints.map((ep) => {
                const isOpen = expandedEpId === ep.id;
                const isActive =
                  ep.kind === "tts"
                    ? draft.active_tts_endpoint_id === ep.id
                    : draft.active_stt_endpoint_id === ep.id;
                const testRes = epTests[ep.id];
                const showKey = !!showExtKeys[ep.id];

                return (
                  <div
                    key={ep.id}
                    className={clsx(
                      "rounded-2xl border transition-colors overflow-hidden",
                      isOpen
                        ? activeEpTab === "tts"
                          ? "border-purple-400/50"
                          : "border-cyan-400/50"
                        : "border-white/10"
                    )}
                    style={{ backgroundColor: "var(--bg-input)" }}
                  >
                    <button
                      type="button"
                      onClick={() => setExpandedEpId(isOpen ? null : ep.id)}
                      className="w-full px-3.5 py-2.5 flex items-center justify-between gap-2 text-left hover:bg-white/5"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {isOpen ? (
                          <ChevronDown className="w-4 h-4 shrink-0 opacity-75" />
                        ) : (
                          <ChevronRight className="w-4 h-4 shrink-0 opacity-75" />
                        )}
                        <span className="text-xs font-semibold truncate">
                          {ep.name || t("settings.unnamedEndpoint")}
                        </span>
                        <span
                          className="text-[11px] font-mono truncate"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {ep.protocol} · {ep.model || "—"}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {isActive && (
                          <span className="rounded-full px-2 py-0.5 text-[10px] font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/35">
                            {t("models.active")}
                          </span>
                        )}
                      </div>
                    </button>

                    {isOpen && (
                      <div className="px-3.5 pb-3.5 pt-2 border-t border-white/10 flex flex-col gap-3">
                        {!ep.base_url && (
                          <div className="flex flex-wrap gap-1.5">
                            {ENDPOINT_PRESETS[ep.kind].map((p) => (
                              <button
                                key={p.key}
                                type="button"
                                onClick={() =>
                                  updateEndpoint(ep.id, {
                                    name: p.name,
                                    protocol: p.protocol,
                                    base_url: p.base_url,
                                    model: p.model,
                                    voice: ep.kind === "tts" ? p.voice : "",
                                  })
                                }
                                className="rounded-full border px-2.5 py-0.5 text-[11px] hover:border-cyan-400/60"
                                style={{
                                  borderColor: "var(--border-glass)",
                                  backgroundColor: "var(--bg-elevated)",
                                }}
                              >
                                {p.label}
                              </button>
                            ))}
                          </div>
                        )}

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          <div className="flex flex-col gap-1">
                            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                              {t("models.epName")}
                            </span>
                            <input
                              value={ep.name}
                              onChange={(e) => updateEndpoint(ep.id, { name: e.target.value })}
                              className="rounded-xl border px-3 py-1.5 text-xs outline-none"
                              style={{
                                backgroundColor: "var(--bg-elevated)",
                                borderColor: "var(--border-glass)",
                              }}
                            />
                          </div>

                          <div className="flex flex-col gap-1">
                            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                              {t("models.epProtocol")}
                            </span>
                            <select
                              value={ep.protocol}
                              onChange={(e) =>
                                updateEndpoint(ep.id, {
                                  protocol: e.target.value as EndpointProtocol,
                                })
                              }
                              className="rounded-xl border px-2.5 py-1.5 text-xs outline-none"
                              style={{
                                backgroundColor: "var(--bg-elevated)",
                                borderColor: "var(--border-glass)",
                                color: "var(--text-primary)",
                              }}
                            >
                              <option value="openai">OpenAI Compatible</option>
                              {ep.kind === "tts" && (
                                <option value="elevenlabs">ElevenLabs</option>
                              )}
                              {ep.kind === "stt" && (
                                <option value="deepgram">Deepgram</option>
                              )}
                            </select>
                          </div>

                          <div className="flex flex-col gap-1">
                            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                              {t("settings.endpointBaseUrl")}
                            </span>
                            <input
                              value={ep.base_url}
                              onChange={(e) => updateEndpoint(ep.id, { base_url: e.target.value })}
                              className="rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                              style={{
                                backgroundColor: "var(--bg-elevated)",
                                borderColor: "var(--border-glass)",
                              }}
                            />
                          </div>

                          <div className="flex flex-col gap-1">
                            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                              {t("settings.endpointApiKey")}
                            </span>
                            <div className="flex items-center gap-1.5">
                              <input
                                type={showKey ? "text" : "password"}
                                value={ep.api_key}
                                onChange={(e) =>
                                  updateEndpoint(ep.id, { api_key: e.target.value })
                                }
                                className="flex-1 rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                                style={{
                                  backgroundColor: "var(--bg-elevated)",
                                  borderColor: "var(--border-glass)",
                                }}
                              />
                              <button
                                type="button"
                                onClick={() =>
                                  setShowExtKeys((prev) => ({ ...prev, [ep.id]: !showKey }))
                                }
                                className="p-1.5 rounded-xl border hover:border-purple-400/50"
                                style={{
                                  borderColor: "var(--border-glass)",
                                  backgroundColor: "var(--bg-elevated)",
                                }}
                              >
                                {showKey ? (
                                  <EyeOff className="w-3.5 h-3.5" />
                                ) : (
                                  <Eye className="w-3.5 h-3.5" />
                                )}
                              </button>
                            </div>
                          </div>

                          <div
                            className={clsx(
                              "flex flex-col gap-1",
                              ep.kind === "stt" && "md:col-span-2"
                            )}
                          >
                            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                              {t("settings.endpointModel")}
                            </span>
                            <input
                              value={ep.model}
                              onChange={(e) => updateEndpoint(ep.id, { model: e.target.value })}
                              className="rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                              style={{
                                backgroundColor: "var(--bg-elevated)",
                                borderColor: "var(--border-glass)",
                              }}
                            />
                          </div>

                          {ep.kind === "tts" && (
                            <div className="flex flex-col gap-1">
                              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                                {t("settings.endpointVoice")}
                              </span>
                              <input
                                value={ep.voice}
                                onChange={(e) => updateEndpoint(ep.id, { voice: e.target.value })}
                                className="rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                                style={{
                                  backgroundColor: "var(--bg-elevated)",
                                  borderColor: "var(--border-glass)",
                                }}
                              />
                            </div>
                          )}
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <BorderBeamButton onClick={() => commit(draft)} activeBeam={false}>
                              {t("settings.save")}
                            </BorderBeamButton>
                            <button
                              type="button"
                              disabled={testingEpId === ep.id || !ep.base_url.trim()}
                              onClick={() => handleTestEp(ep)}
                              className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium hover:border-cyan-400/50 disabled:opacity-40"
                              style={{
                                borderColor: "var(--border-glass)",
                                backgroundColor: "var(--bg-elevated)",
                              }}
                            >
                              <Zap className="w-3.5 h-3.5" />
                              {t("settings.testConnection")}
                            </button>
                            {!isActive && (
                              <button
                                type="button"
                                onClick={() => handleSetActiveEp(ep)}
                                className="inline-flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-medium hover:border-emerald-400/50 text-emerald-300"
                                style={{
                                  borderColor: "var(--border-glass)",
                                  backgroundColor: "var(--bg-elevated)",
                                }}
                              >
                                <Check className="w-3.5 h-3.5" />
                                {t("settings.setActive")}
                              </button>
                            )}
                            {testRes && (
                              <span
                                className={clsx(
                                  "text-xs font-mono",
                                  testRes.ok ? "text-emerald-300" : "text-rose-300"
                                )}
                              >
                                {testRes.ok
                                  ? `HTTP ${testRes.status_code} · ${testRes.latency_ms}ms`
                                  : `FAIL (${testRes.status_code}): ${testRes.detail}`}
                              </span>
                            )}
                          </div>

                          <button
                            type="button"
                            onClick={() => handleDeleteEp(ep)}
                            className="inline-flex items-center gap-1 rounded-full border border-rose-500/50 bg-rose-500/15 px-3 py-1.5 text-xs font-medium text-rose-200 hover:bg-rose-500/25"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            {t("profiles.delete")}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
};
