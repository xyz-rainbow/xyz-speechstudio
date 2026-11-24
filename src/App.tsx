import { Component, type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { AsciiAmbientPool } from "./components/AsciiAmbientPool";
import { CloseConfirmModal } from "./components/CloseConfirmModal";
import { ModelsView } from "./components/ModelsView";
import { ProfilesView } from "./components/ProfilesView";
import { SettingsView } from "./components/SettingsView";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { SubtitlesView } from "./components/SubtitlesView";
import { TranscriberView } from "./components/TranscriberView";
import { TtsStudioView } from "./components/TtsStudioView";
import { UpdatesView } from "./components/UpdateBadge";
import { I18nProvider, useI18n } from "./i18n";
import {
  ejectWorkerGroup,
  fetchHistory,
  fetchModelsCatalog,
  fetchPendingToasts,
  fetchProfiles,
  fetchSettings,
  fetchWorkers,
  getBackendInfo,
  getVramStatus,
  hideMainWindow,
  isTauri,
  notify,
  quitApp,
  saveSettings,
  sendWindowsToast,
  setCaptionsLock,
  stopLiveCaptions,
  updateTrayMenu,
} from "./services/api";
import type {
  AppSettings,
  BackendInfo,
  CatalogModelEntry,
  GenerationRecord,
  TabId,
  VoiceProfile,
  VramStatus,
  WorkersSnapshot,
} from "./types";

const DEFAULT_SETTINGS: AppSettings = {
  language: "en",
  theme: "dark",
  accent: "cyber",
  ascii_fx_enabled: true,
  ascii_fx_opacity: 0.13,
  sidebar_collapsed: false,
  models_dir: "",
  outputs_dir: "",
  tts_device: "gpu",
  stt_device: "gpu",
  tts_source: "local",
  stt_source: "local",
  active_tts_model: "qwen3-1.7b-base-Q8_0",
  active_stt_model: "faster-whisper-base",
  active_tts_endpoint_id: "",
  active_stt_endpoint_id: "",
  captions_max_history: 20,
  notifications_enabled: true,
  api_endpoint_enabled: false,
  api_fixed_port: 0,
  api_bind_host: "127.0.0.1",
  api_bearer_token: "",
  read_hotkey: "",
  close_behavior: "ask",
  external_endpoints: [],
  capabilities_v1: true,
  installed_languages: {},
};

function MainStudio() {
  const { t, setLang } = useI18n();
  const [activeTab, setActiveTab] = useState<TabId>("synthesize");
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [resolvedModelsDir, setResolvedModelsDir] = useState("data/models");
  const [resolvedOutputsDir, setResolvedOutputsDir] = useState("data/outputs");
  const [profiles, setProfiles] = useState<VoiceProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [closePromptOpen, setClosePromptOpen] = useState(false);
  const [history, setHistory] = useState<GenerationRecord[]>([]);
  const [vram, setVram] = useState<VramStatus>({
    available: false,
    gpu: "Detecting...",
    total_mib: 0,
    used_mib: 0,
    free_mib: 0,
  });
  const [backend, setBackend] = useState<BackendInfo>({
    running: false,
    port: 0,
    pid: 0,
    base_url: "",
    live_captions_supported: false,
    read_selection_supported: false,
  });
  const [workers, setWorkers] = useState<WorkersSnapshot | null>(null);
  const [catalog, setCatalog] = useState<CatalogModelEntry[]>([]);

  useEffect(() => {
    document.body.classList.remove("app-overlay");
    document.body.classList.add("app-main");
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", settings.theme);
    document.documentElement.setAttribute("data-accent", settings.accent);
    setLang(settings.language);
  }, [settings.theme, settings.accent, settings.language, setLang]);

  const refreshSystem = useCallback(async () => {
    try {
      const [v, b] = await Promise.all([getVramStatus(), getBackendInfo()]);
      setVram(v);
      setBackend(b);
      if (b.running && b.base_url) {
        const [w, catalogRes, pending] = await Promise.all([
          fetchWorkers(b.base_url).catch(() => null),
          fetchModelsCatalog(b.base_url).catch(() => null),
          fetchPendingToasts(b.base_url).catch(() => []),
        ]);
        if (w) setWorkers(w);
        if (catalogRes) setCatalog(catalogRes.models);
        for (const item of pending) {
          await sendWindowsToast(
            item.title,
            item.message,
            item.progress == null ? undefined : item.progress
          ).catch(() => {});
        }
      }
    } catch {
      // ignore transient startup polling errors
    }
  }, []);

  useEffect(() => {
    let alive = true;
    const init = async () => {
      const b = await getBackendInfo();
      if (!alive) return;
      setBackend(b);
      if (b.running && b.base_url) {
        try {
          const [s, profs, hist] = await Promise.all([
            fetchSettings(b.base_url),
            fetchProfiles(b.base_url),
            fetchHistory(b.base_url),
          ]);
          if (!alive) return;
          setSettings(s.settings);
          setResolvedModelsDir(s.resolved_models_dir);
          setResolvedOutputsDir(s.resolved_outputs_dir);
          setProfiles(profs);
          if (profs.length > 0 && !profs.some((p) => p.id === "mario")) {
            setSelectedProfileId(profs[0].id);
          }
          setHistory(hist);
        } catch {
          // ignore
        }
      }
      await refreshSystem();
    };
    init();
    const timer = setInterval(refreshSystem, 2500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [refreshSystem]);

  const handleSaveSettings = async (next: AppSettings) => {
    setSettings(next);
    if (backend.running && backend.base_url) {
      const res = await saveSettings(backend.base_url, next);
      setSettings(res.settings);
      setResolvedModelsDir(res.resolved_models_dir);
      setResolvedOutputsDir(res.resolved_outputs_dir);
    }
  };

  const [incomingSpeak, setIncomingSpeak] = useState<{ text: string; nonce: number } | null>(
    null
  );
  const baseUrlRef = useRef("");
  baseUrlRef.current = backend.base_url;
  const notificationsRef = useRef(true);
  notificationsRef.current = settings.notifications_enabled;
  const tRef = useRef(t);
  tRef.current = t;

  // Windows: UI Automation. Linux: primary selection only, never the clipboard.
  useEffect(() => {
    if (!isTauri()) return;
    let unlisten: (() => void) | undefined;
    listen<{ text?: string; code?: string } | string | null>("read-selection", (ev) => {
      const payload = ev.payload;
      let code = "empty";
      let text = "";
      if (typeof payload === "string") {
        text = payload;
        code = payload.trim() ? "text" : "empty";
      } else if (payload && typeof payload === "object") {
        text = payload.text ?? "";
        code = payload.code ?? (text.trim() ? "text" : "empty");
      }
      if (code === "unavailable") {
        const translate = tRef.current;
        void notify(
          notificationsRef.current,
          translate("toast.title"),
          translate("hotkey.selectionTools")
        );
        return;
      }
      setActiveTab("synthesize");
      setIncomingSpeak((prev) => ({ text, nonce: (prev?.nonce ?? 0) + 1 }));
    }).then((fn) => {
      unlisten = fn;
    });
    return () => unlisten?.();
  }, []);

  // Window close confirmation popup / saved close behavior
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  useEffect(() => {
    if (!isTauri()) return;
    let unlisten: (() => void) | undefined;
    listen("close-requested", () => {
      const behavior = settingsRef.current.close_behavior;
      if (behavior === "minimize") {
        void hideMainWindow();
      } else if (behavior === "quit") {
        void quitApp();
      } else {
        setClosePromptOpen(true);
      }
    }).then((fn) => {
      unlisten = fn;
    });
    return () => unlisten?.();
  }, []);

  // Tray menu actions.
  useEffect(() => {
    if (!isTauri()) return;
    let unlisten: (() => void) | undefined;
    listen<string>("tray-action", async (ev) => {
      const base = baseUrlRef.current;
      if (ev.payload === "subtitles") {
        setActiveTab("subtitles");
      } else if (ev.payload === "stop_subtitles" && base) {
        await stopLiveCaptions().catch(() => {});
        await setCaptionsLock(base, false).catch(() => {});
        refreshSystem();
        void notify(settings.notifications_enabled, t("toast.title"), t("toast.captionsOff"));
      } else if (ev.payload === "eject" && base) {
        await ejectWorkerGroup(base, "tts").catch(() => {});
        await ejectWorkerGroup(base, "stt").catch(() => {});
        refreshSystem();
        void notify(settings.notifications_enabled, t("toast.title"), t("toast.ejected"));
      }
    }).then((fn) => {
      unlisten = fn;
    });
    return () => unlisten?.();
  }, [refreshSystem, settings.notifications_enabled, t]);

  // Keep tray labels localized and in sync with Live Captions state.
  const captionsActive = !!workers?.live_captions_active;
  useEffect(() => {
    updateTrayMenu({
      open: t("tray.open"),
      show_hide: t("tray.showHide"),
      subtitles: t("tray.subtitles"),
      stop_subtitles: t("tray.stopSubtitles"),
      eject: t("tray.eject"),
      exit: t("tray.exit"),
      subtitles_active: captionsActive,
    }).catch(() => {});
  }, [settings.language, captionsActive]);

  return (
    <div className="relative w-screen h-screen overflow-hidden flex p-2.5 gap-2.5">
      <AsciiAmbientPool
        enabled={settings.ascii_fx_enabled}
        opacity={settings.ascii_fx_opacity}
        theme={settings.theme}
        accent={settings.accent}
      />

      <Sidebar
        activeTab={activeTab}
        collapsed={settings.sidebar_collapsed}
        baseUrl={backend.base_url}
        onSelectTab={setActiveTab}
        onToggleCollapse={() =>
          handleSaveSettings({ ...settings, sidebar_collapsed: !settings.sidebar_collapsed })
        }
      />

      <div className="relative z-10 flex-1 min-w-0 flex flex-col gap-2.5">
        <TopBar
          vram={vram}
          ttsDevice={settings.tts_device}
          sttDevice={settings.stt_device}
          ttsSource={settings.tts_source}
          sttSource={settings.stt_source}
          theme={settings.theme}
          onChangeTtsDevice={(d) => handleSaveSettings({ ...settings, tts_device: d })}
          onChangeSttDevice={(d) => handleSaveSettings({ ...settings, stt_device: d })}
          onToggleTheme={() =>
            handleSaveSettings({
              ...settings,
              theme: settings.theme === "dark" ? "light" : "dark",
            })
          }
        />

        <main className="flex-1 min-h-0 flex flex-col overflow-y-auto pr-1">
          <div
            className={activeTab === "synthesize" ? "flex-1 min-h-0 flex flex-col" : "hidden"}
          >
            <TtsStudioView
              baseUrl={backend.base_url}
              catalog={catalog}
              settings={settings}
              onSaveSettings={handleSaveSettings}
              profiles={profiles}
              selectedProfileId={selectedProfileId}
              onSelectProfileId={setSelectedProfileId}
              history={history}
              onHistoryChange={setHistory}
              onAfterGpuAction={refreshSystem}
              incomingSpeak={incomingSpeak}
              notificationsEnabled={settings.notifications_enabled}
              onOpenModels={() => setActiveTab("models")}
              onOpenProfiles={() => setActiveTab("profiles")}
              onCatalogChange={setCatalog}
              onInstalledLanguagesChange={(next) =>
                void handleSaveSettings({ ...settings, installed_languages: next })
              }
            />
          </div>

          {activeTab === "profiles" && (
            <ProfilesView
              baseUrl={backend.base_url}
              catalog={catalog}
              settings={settings}
              profiles={profiles}
              selectedProfileId={selectedProfileId}
              onProfilesChange={setProfiles}
              onUseProfile={(id) => {
                setSelectedProfileId(id);
                setActiveTab("synthesize");
              }}
              onAfterGpuAction={refreshSystem}
              notificationsEnabled={settings.notifications_enabled}
            />
          )}

          {activeTab === "transcriber" && (
            <TranscriberView
              baseUrl={backend.base_url}
              catalog={catalog}
              settings={settings}
              onSaveSettings={handleSaveSettings}
              onAfterGpuAction={refreshSystem}
            />
          )}

          {activeTab === "subtitles" && (
            <SubtitlesView
              baseUrl={backend.base_url}
              settings={settings}
              onAfterGpuAction={refreshSystem}
              liveCaptionsSupported={backend.live_captions_supported}
            />
          )}

          {activeTab === "models" && (
            <ModelsView
              baseUrl={backend.base_url}
              settings={settings}
              workers={workers}
              vram={vram}
              onSaveSettings={handleSaveSettings}
              onWorkersChange={setWorkers}
              onCatalogChange={setCatalog}
              onAfterGpuAction={refreshSystem}
            />
          )}

          {activeTab === "settings" && (
            <SettingsView
              settings={settings}
              resolvedModelsDir={resolvedModelsDir}
              resolvedOutputsDir={resolvedOutputsDir}
              apiBaseUrl={backend.base_url || "http://127.0.0.1:0"}
              apiRunning={backend.running}
              apiPort={backend.port}
              readSelectionSupported={backend.read_selection_supported}
              onSave={handleSaveSettings}
            />
          )}

          {activeTab === "updates" && <UpdatesView baseUrl={backend.base_url} />}
        </main>
      </div>

      <CloseConfirmModal
        open={closePromptOpen}
        onCancel={() => setClosePromptOpen(false)}
        onMinimize={async (remember) => {
          setClosePromptOpen(false);
          if (remember) {
            await handleSaveSettings({ ...settings, close_behavior: "minimize" }).catch(() => {});
          }
          await hideMainWindow();
        }}
        onQuit={async (remember) => {
          setClosePromptOpen(false);
          if (remember) {
            await handleSaveSettings({ ...settings, close_behavior: "quit" }).catch(() => {});
          }
          await quitApp();
        }}
      />
    </div>
  );
}

class AppErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="w-screen h-screen flex items-center justify-center bg-[#09090f] text-slate-100 p-6">
          <div className="max-w-md w-full rounded-2xl border border-rose-500/40 bg-rose-950/20 p-5 flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-rose-300">Speech Studio UI Error</h2>
            <p className="text-xs font-mono text-slate-300 break-words">
              {this.state.error.message}
            </p>
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
              className="self-start rounded-xl border border-white/20 px-3 py-1.5 text-xs font-medium hover:bg-white/10"
            >
              Reload view
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [lang, setLang] = useState<"en" | "es">("en");
  return (
    <AppErrorBoundary>
      <I18nProvider lang={lang} setLang={setLang}>
        <MainStudio />
      </I18nProvider>
    </AppErrorBoundary>
  );
}
