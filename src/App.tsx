import { useCallback, useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { Captions } from "lucide-react";
import { AsciiAmbientPool } from "./components/AsciiAmbientPool";
import { BorderBeamButton } from "./components/BorderBeamButton";
import { GlassCard } from "./components/GlassCard";
import { ModelsView } from "./components/ModelsView";
import { ProfilesView } from "./components/ProfilesView";
import { SettingsView } from "./components/SettingsView";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { TranscriberView } from "./components/TranscriberView";
import { TtsStudioView } from "./components/TtsStudioView";
import { I18nProvider, useI18n } from "./i18n";
import {
  ejectWorkerGroup,
  fetchHistory,
  fetchProfiles,
  fetchSettings,
  fetchWorkers,
  getBackendInfo,
  getVramStatus,
  isTauri,
  saveSettings,
  toggleOverlayWindow,
  updateTrayMenu,
} from "./services/api";
import type {
  AppSettings,
  BackendInfo,
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
  external_endpoints: [],
};

function MainStudio() {
  const { t, setLang } = useI18n();
  const [activeTab, setActiveTab] = useState<TabId>("synthesize");
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [resolvedModelsDir, setResolvedModelsDir] = useState("data/models");
  const [resolvedOutputsDir, setResolvedOutputsDir] = useState("data/outputs");
  const [profiles, setProfiles] = useState<VoiceProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState("mario");
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
  });
  const [workers, setWorkers] = useState<WorkersSnapshot | null>(null);

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
        const w = await fetchWorkers(b.base_url);
        setWorkers(w);
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

  // Global hotkey: selected text read by the Rust side via UI Automation (clipboard untouched).
  useEffect(() => {
    if (!isTauri()) return;
    let unlisten: (() => void) | undefined;
    listen<string | null>("read-selection", (ev) => {
      setActiveTab("synthesize");
      setIncomingSpeak((prev) => ({ text: ev.payload ?? "", nonce: (prev?.nonce ?? 0) + 1 }));
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
        await fetch(`${base}/api/captions/lock`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active: false }),
        }).catch(() => {});
        refreshSystem();
      } else if (ev.payload === "eject" && base) {
        await ejectWorkerGroup(base, "tts").catch(() => {});
        await ejectWorkerGroup(base, "stt").catch(() => {});
        refreshSystem();
      }
    }).then((fn) => {
      unlisten = fn;
    });
    return () => unlisten?.();
  }, [refreshSystem]);

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
              profiles={profiles}
              selectedProfileId={selectedProfileId}
              onSelectProfileId={setSelectedProfileId}
              history={history}
              onHistoryChange={setHistory}
              onAfterGpuAction={refreshSystem}
              incomingSpeak={incomingSpeak}
            />
          </div>

          {activeTab === "profiles" && (
            <ProfilesView
              baseUrl={backend.base_url}
              profiles={profiles}
              selectedProfileId={selectedProfileId}
              onProfilesChange={setProfiles}
              onUseProfile={(id) => {
                setSelectedProfileId(id);
                setActiveTab("synthesize");
              }}
              onAfterGpuAction={refreshSystem}
            />
          )}

          {activeTab === "transcriber" && (
            <TranscriberView
              baseUrl={backend.base_url}
              settings={settings}
              onSaveSettings={handleSaveSettings}
              onAfterGpuAction={refreshSystem}
            />
          )}

          {activeTab === "subtitles" && (
            <GlassCard className="p-5 flex flex-col gap-3">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <h1 className="text-lg font-semibold">{t("subtitles.title")}</h1>
                  <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                    {t("subtitles.subtitle")}
                  </p>
                </div>
                <BorderBeamButton onClick={() => toggleOverlayWindow()}>
                  <Captions className="w-4 h-4" />
                  {t("subtitles.overlay")}
                </BorderBeamButton>
              </div>
              <div
                className="rounded-2xl border p-3.5 text-xs"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-input)",
                  color: "var(--text-secondary)",
                }}
              >
                {t("subtitles.testOverlayHint")}
              </div>
            </GlassCard>
          )}

          {activeTab === "models" && (
            <ModelsView
              baseUrl={backend.base_url}
              settings={settings}
              workers={workers}
              vram={vram}
              onSaveSettings={handleSaveSettings}
              onWorkersChange={setWorkers}
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
              onSave={handleSaveSettings}
            />
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const [lang, setLang] = useState<"en" | "es">("en");
  return (
    <I18nProvider lang={lang} setLang={setLang}>
      <MainStudio />
    </I18nProvider>
  );
}
