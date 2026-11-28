import assert from "node:assert/strict";
import crypto from "node:crypto";
import http from "node:http";
import test from "node:test";

import {
  buildPublishApiPayload,
  fetchPersonaCatalog,
  fetchPersonaInstallProgress,
  filterPersonas,
  installRemotePersona,
  isPersonaDemoOnly,
  LOCAL_PREVIEW_PERSONAS,
  PersonaClientError,
  resolvePersonaInstallStatus,
  restoreProfileOriginalAudio,
  switchProfileEngine,
  validatePersonaLibraryUrl,
  validatePublishDraft,
} from "../src/services/personaClient.ts";
import {
  evaluateAudioForEngine,
  evaluatePersonaAgainstCatalog,
} from "../src/utils/personaCompatibility.ts";

test("validatePersonaLibraryUrl accepts http/https and rejects invalid schemes", () => {
  const ok = validatePersonaLibraryUrl("  https://persona.k3s.local/api/  ");
  assert.equal(ok.valid, true);
  assert.equal(ok.normalized, "https://persona.k3s.local/api");

  const empty = validatePersonaLibraryUrl("   ");
  assert.equal(empty.valid, false);

  const badScheme = validatePersonaLibraryUrl("ftp://persona.k3s.local");
  assert.equal(badScheme.valid, false);

  const scriptScheme = validatePersonaLibraryUrl("javascript:alert(1)");
  assert.equal(scriptScheme.valid, false);
});

test("filterPersonas filters by search text, language, and origin", () => {
  const spanishShared = filterPersonas(LOCAL_PREVIEW_PERSONAS, {
    language: "Spanish",
    origin: "shared",
  });
  assert.equal(spanishShared.length, 1);
  assert.equal(spanishShared[0].id, "preview-es-podcast-shared");

  const byTag = filterPersonas(LOCAL_PREVIEW_PERSONAS, { search: "flac" });
  assert.equal(byTag.length, 1);
  assert.equal(byTag[0].language, "French");
});

test("fetchPersonaCatalog returns clearly labeled local preview data", async () => {
  const res = await fetchPersonaCatalog({ source_mode: "local_preview", library_url: "" });
  assert.equal(res.source_mode, "local_preview");
  assert.equal(res.server_url, null);
  assert.equal(res.warning, "preview_mode");
  assert.ok(res.items.length >= 4);
});

test("fetchPersonaCatalog handles remote_k3s success and typed errors cleanly", async () => {
  const remoteConfig = {
    source_mode: "remote_k3s",
    library_url: "https://persona.k3s.internal/",
  };

  // Unconfigured or invalid URL fails before network call
  await assert.rejects(
    () => fetchPersonaCatalog({ source_mode: "remote_k3s", library_url: "" }),
    (err) => err instanceof PersonaClientError && err.code === "UNCONFIGURED_URL"
  );

  // Successful remote response
  const okRes = await fetchPersonaCatalog(remoteConfig, {}, async (url) => {
    assert.equal(url, "https://persona.k3s.internal/v1/personas");
    return new Response(
      JSON.stringify({
        api_version: "v1",
        total: 1,
        items: [LOCAL_PREVIEW_PERSONAS[0]],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  });
  assert.equal(okRes.source_mode, "remote_k3s");
  assert.equal(okRes.server_url, "https://persona.k3s.internal");
  assert.equal(okRes.items.length, 1);

  // Auth error (401)
  await assert.rejects(
    () =>
      fetchPersonaCatalog(remoteConfig, {}, async () =>
        new Response(JSON.stringify({ detail: "Token missing" }), { status: 401 })
      ),
    (err) => err instanceof PersonaClientError && err.code === "AUTH_REQUIRED"
  );

  // Unreachable server
  await assert.rejects(
    () =>
      fetchPersonaCatalog(remoteConfig, {}, async () => {
        throw new Error("ECONNREFUSED");
      }),
    (err) => err instanceof PersonaClientError && err.code === "UNREACHABLE_SERVER"
  );

  // Malformed response payload
  await assert.rejects(
    () =>
      fetchPersonaCatalog(remoteConfig, {}, async () =>
        new Response(JSON.stringify({ wrong: true }), { status: 200 })
      ),
    (err) => err instanceof PersonaClientError && err.code === "INVALID_RESPONSE"
  );
});

test("validatePublishDraft requires metadata, audio, transcript, and consent", () => {
  const incomplete = validatePublishDraft({
    name: "Test Voice",
    language: "Spanish",
    locale: "es-ES",
    description: "",
    ref_audio_path: "",
    ref_text: "",
    tags: [],
    provenance_type: "self_recorded",
    provenance_note: "",
    license: "cc-by-4.0",
    attribution: "",
    speaker_consent_confirmed: false,
  });
  assert.equal(incomplete.valid, false);
  assert.ok(incomplete.errors.includes("missing_consent"));
  assert.ok(incomplete.errors.includes("missing_audio"));

  const completeDraft = {
    name: "Clara Demo",
    language: "Spanish",
    locale: "es-ES",
    description: "Warm studio voice recorded for local TTS narration.",
    ref_audio_path: "C:\\voices\\clara.wav",
    ref_text: "Hola, esto es una muestra de voz para probar el perfil.",
    tags: ["studio", "es-ES"],
    provenance_type: "self_recorded",
    provenance_note: "Recorded at home",
    license: "cc-by-4.0",
    attribution: "Clara",
    speaker_consent_confirmed: true,
  };
  const validCheck = validatePublishDraft(completeDraft);
  assert.equal(validCheck.valid, true);
  assert.equal(validCheck.errors.length, 0);

  const payload = buildPublishApiPayload(completeDraft);
  assert.equal(payload.api_version, "v1");
  assert.equal(payload.audio.upload_pending_backend, true);
  assert.equal(payload.consent.speaker_consent_confirmed, true);
});

test("compatibility matrix shows exact conversions and rejects non-cloning engines", () => {
  const podcastSample = LOCAL_PREVIEW_PERSONAS.find((p) => p.id === "preview-es-podcast-shared");
  assert.ok(podcastSample);

  const f5Eval = evaluateAudioForEngine("f5", podcastSample.audio, podcastSample.ref_text, {
    installed: true,
  });
  assert.equal(f5Eval.supports_cloning, true);
  assert.equal(f5Eval.status, "needs_conversion");
  assert.ok(f5Eval.conversions_needed.some((c) => c.includes("MP3")));
  assert.ok(f5Eval.conversions_needed.some((c) => c.includes("2ch")));
  assert.ok(f5Eval.conversions_needed.some((c) => c.includes("Trim")));

  const piperEval = evaluateAudioForEngine("piper", podcastSample.audio, podcastSample.ref_text, {
    installed: true,
  });
  assert.equal(piperEval.supports_cloning, false);
  assert.equal(piperEval.status, "unsupported_no_cloning");
  assert.equal(piperEval.conversions_needed.length, 0);

  const catalogMock = [
    {
      id: "piper-es",
      name: "Piper",
      kind: "tts",
      engine: "piper",
      family_id: "piper",
      family_name: "Piper",
      variant_label: "Piper",
      repo_id: "",
      description: "",
      runtime_supported: true,
      capabilities: {
        install_mode: "shared_weights",
        voice_mode: "builtin_voices",
        quant_policy: "onnx",
        languages: ["es"],
      },
      quants: [],
      installed: true,
      installed_quant: null,
      installed_quants: [],
      install_dir: null,
      external: false,
      removable: false,
      custom: false,
      disk_mb: 50,
      vram_mib: 0,
    },
    {
      id: "qwen3-1.7b-base",
      name: "Qwen3-TTS 1.7B",
      kind: "tts",
      engine: "qwen",
      family_id: "qwen3",
      family_name: "Qwen3-TTS",
      variant_label: "1.7B Base",
      repo_id: "",
      description: "",
      runtime_supported: true,
      capabilities: {
        install_mode: "shared_weights",
        voice_mode: "clone_profile",
        quant_policy: "gguf",
        languages: ["es", "en"],
      },
      quants: [],
      installed: true,
      installed_quant: "Q4_K_M",
      installed_quants: ["Q4_K_M"],
      install_dir: "C:\\models\\qwen",
      external: false,
      removable: true,
      custom: false,
      disk_mb: 1200,
      vram_mib: 2200,
    },
  ];

  const againstPiper = evaluatePersonaAgainstCatalog(
    podcastSample,
    catalogMock,
    "piper-es"
  );
  assert.equal(againstPiper.active?.status, "unsupported_no_cloning");
  assert.equal(againstPiper.preferredCloneEngine, "qwen");
  assert.equal(againstPiper.unsupported.length, 1);
});

test("demo-only preview cards are never marked installed without a real VoiceProfile", () => {
  const demoCard = LOCAL_PREVIEW_PERSONAS[0];
  assert.equal(isPersonaDemoOnly(demoCard, "local_preview"), true);
  assert.equal(isPersonaDemoOnly(demoCard, "remote_k3s"), true);

  const remoteCard = {
    ...demoCard,
    audio: {
      ...demoCard.audio,
      download_url: "https://persona.k3s.local/v1/personas/p1/audio",
      sha256: "a".repeat(64),
    },
  };
  assert.equal(isPersonaDemoOnly(remoteCard, "remote_k3s"), false);

  // Without matching real VoiceProfile, resolvePersonaInstallStatus must stay false
  const notInstalled = resolvePersonaInstallStatus(demoCard, []);
  assert.equal(notInstalled.installed, false);
  assert.equal(notInstalled.mode, null);

  // Disambiguated profile still counts as an installed real VoiceProfile
  const disambiguated = resolvePersonaInstallStatus(demoCard, [
    {
      id: "alvaro-persona",
      name: `${demoCard.name} (Persona)`,
      language: "Spanish",
      engine: "qwen",
      ref_audio_path: "data/profiles/alvaro-persona/ref.wav",
      ref_text: "Hola",
      spk_path: "",
      rvq_path: "",
      ready: true,
      created_at: 1,
      updated_at: 1,
    },
  ]);
  assert.equal(disambiguated.installed, true);
  assert.equal(disambiguated.mode, "profile");
  assert.equal(disambiguated.profileId, "alvaro-persona");
});

test("installRemotePersona and fetchPersonaInstallProgress handle local bridge responses", async () => {
  const reqPayload = {
    persona_id: "es-alvaro",
    name: "Álvaro",
    language: "Spanish",
    engine: "qwen",
    ref_text: "Hola",
    library_url: "https://persona.k3s.local",
    download_url: "/v1/personas/es-alvaro/audio",
    sha256: "b".repeat(64),
    audio_format: "wav",
  };

  const ok = await installRemotePersona("http://127.0.0.1:8765/", reqPayload, async (url) => {
    assert.equal(url, "http://127.0.0.1:8765/api/persona/install-remote");
    return new Response(
      JSON.stringify({
        profile: {
          id: "alvaro-persona",
          name: "Álvaro (Persona)",
          language: "Spanish",
          engine: "qwen",
          ref_audio_path: "data/profiles/alvaro-persona/ref.wav",
          ref_text: "Hola",
          spk_path: "",
          rvq_path: "",
          ready: true,
          created_at: 1,
          updated_at: 1,
        },
        persona_id: "es-alvaro",
        sha256: "b".repeat(64),
        size_bytes: 4096,
        audio_format: "wav",
        name_disambiguated: true,
        original_name: "Álvaro",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  });
  assert.equal(ok.name_disambiguated, true);
  assert.equal(ok.profile.id, "alvaro-persona");

  await assert.rejects(
    () =>
      installRemotePersona("http://127.0.0.1:8765", reqPayload, async () =>
        new Response(
          JSON.stringify({ code: "sha256_mismatch", detail: "Hash mismatch" }),
          { status: 422 }
        )
      ),
    (err) => err instanceof PersonaClientError && err.backendCode === "sha256_mismatch"
  );

  await assert.rejects(
    () =>
      installRemotePersona("http://127.0.0.1:8765", reqPayload, async () =>
        new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 })
      ),
    (err) => err instanceof PersonaClientError && err.code === "BACKEND_REQUIRED"
  );

  const prog = await fetchPersonaInstallProgress("http://127.0.0.1:8765", async (url) => {
    assert.equal(url, "http://127.0.0.1:8765/api/persona/install-progress");
    return new Response(
      JSON.stringify({ phase: "verifying", persona_id: "es-alvaro", downloaded: 4096, total: 4096 }),
      { status: 200 }
    );
  });
  assert.equal(prog?.phase, "verifying");

  const missingProg = await fetchPersonaInstallProgress("http://127.0.0.1:8765", async () =>
    new Response("", { status: 404 })
  );
  assert.equal(missingProg, null);
});

test("end-to-end localhost HTTP server covers Persona catalog, install, switch-engine, and restore", async () => {
  const wavPayload = Buffer.from("RIFF\x24\x00\x00\x00WAVEfmt ", "latin1");
  const expectedSha = crypto.createHash("sha256").update(wavPayload).digest("hex");
  let installedProfiles = [];
  let currentProgress = { phase: "idle", persona_id: "", downloaded: 0, total: 0 };

  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const bodyStr = Buffer.concat(chunks).toString("utf-8");
      if (req.method === "GET" && req.url === "/v1/personas") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(
          JSON.stringify({
            api_version: "v1",
            total: 1,
            items: [
              {
                ...LOCAL_PREVIEW_PERSONAS[0],
                id: "k3s-live-demo",
                slug: "k3s-live-demo",
                name: "Álvaro Live",
                audio: {
                  format: "wav",
                  sample_rate_hz: 24000,
                  channels: 1,
                  duration_s: 8.6,
                  sha256: expectedSha,
                  size_bytes: wavPayload.length,
                  download_url: "/v1/personas/k3s-live-demo/audio",
                },
              },
            ],
          })
        );
        return;
      }

      if (req.method === "POST" && req.url === "/api/persona/install-remote") {
        const parsed = JSON.parse(bodyStr);
        currentProgress = {
          phase: "done",
          persona_id: parsed.persona_id,
          downloaded: wavPayload.length,
          total: wavPayload.length,
        };
        const created = {
          id: "alvaro-live",
          name: parsed.name,
          language: parsed.language,
          engine: parsed.engine,
          ref_audio_path: "data/profiles/alvaro-live/ref.wav",
          ref_original_path: "data/profiles/alvaro-live/ref.wav",
          ref_trimmed: false,
          ref_text: parsed.ref_text,
          spk_path: "",
          rvq_path: "",
          ready: true,
          created_at: 1,
          updated_at: 1,
        };
        installedProfiles = [created];
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(
          JSON.stringify({
            profile: created,
            persona_id: parsed.persona_id,
            sha256: expectedSha,
            size_bytes: wavPayload.length,
            audio_format: "wav",
            name_disambiguated: false,
            original_name: parsed.name,
          })
        );
        return;
      }

      if (req.method === "GET" && req.url === "/api/persona/install-progress") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(currentProgress));
        return;
      }

      if (req.method === "POST" && req.url === "/api/profiles/alvaro-live/switch-engine") {
        const parsed = JSON.parse(bodyStr);
        installedProfiles[0] = { ...installedProfiles[0], engine: parsed.engine };
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ profile: installedProfiles[0] }));
        return;
      }

      if (req.method === "POST" && req.url === "/api/profiles/alvaro-live/restore-original") {
        installedProfiles[0] = {
          ...installedProfiles[0],
          ref_trimmed: false,
          ref_audio_path: installedProfiles[0].ref_original_path,
        };
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ profile: installedProfiles[0] }));
        return;
      }

      res.writeHead(404);
      res.end();
    });
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const port = server.address().port;
    const baseUrl = `http://127.0.0.1:${port}`;

    const cat = await fetchPersonaCatalog({ source_mode: "remote_k3s", library_url: baseUrl });
    assert.equal(cat.items.length, 1);
    assert.equal(isPersonaDemoOnly(cat.items[0], "remote_k3s"), false);
    assert.equal(resolvePersonaInstallStatus(cat.items[0], installedProfiles).installed, false);

    const installed = await installRemotePersona(baseUrl, {
      persona_id: cat.items[0].id,
      name: cat.items[0].name,
      language: cat.items[0].language,
      engine: "qwen",
      ref_text: cat.items[0].ref_text,
      library_url: baseUrl,
      download_url: cat.items[0].audio.download_url,
      sha256: cat.items[0].audio.sha256,
      audio_format: "wav",
      expected_size_bytes: wavPayload.length,
    });
    assert.equal(installed.sha256, expectedSha);
    assert.equal(resolvePersonaInstallStatus(cat.items[0], [installed.profile]).installed, true);

    // Demo card must remain NOT installed even after remote install above
    assert.equal(resolvePersonaInstallStatus(LOCAL_PREVIEW_PERSONAS[1], [installed.profile]).installed, false);

    const prog = await fetchPersonaInstallProgress(baseUrl);
    assert.equal(prog?.phase, "done");

    const switched = await switchProfileEngine(baseUrl, "alvaro-live", "f5", true);
    assert.equal(switched.engine, "f5");
    assert.equal(switched.ref_original_path, "data/profiles/alvaro-live/ref.wav");

    const restored = await restoreProfileOriginalAudio(baseUrl, "alvaro-live");
    assert.equal(restored.ref_trimmed, false);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
