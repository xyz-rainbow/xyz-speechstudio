import { invoke } from "@tauri-apps/api/core";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { isTauri } from "./api";

export interface DialogFilter {
  name: string;
  extensions: string[];
}

export async function pickFile(options?: {
  title?: string;
  filters?: DialogFilter[];
}): Promise<string | null> {
  if (!isTauri()) return null;
  try {
    const res = await invoke<string | null>("pick_path", {
      directory: false,
      title: options?.title ?? null,
      filters: options?.filters ?? [],
    });
    return res ?? null;
  } catch {
    const fallback = await openDialog({
      multiple: false,
      directory: false,
      title: options?.title,
      filters: options?.filters,
    });
    return typeof fallback === "string" && fallback.length > 0 ? fallback : null;
  }
}

export async function pickFolder(options?: { title?: string }): Promise<string | null> {
  if (!isTauri()) return null;
  try {
    const res = await invoke<string | null>("pick_path", {
      directory: true,
      title: options?.title ?? null,
      filters: [],
    });
    return res ?? null;
  } catch {
    const fallback = await openDialog({
      multiple: false,
      directory: true,
      title: options?.title,
    });
    return typeof fallback === "string" && fallback.length > 0 ? fallback : null;
  }
}
