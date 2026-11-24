import React, { createContext, useContext } from "react";
import en from "./locales/en.json";
import es from "./locales/es.json";

export type LanguageCode = "en" | "es";

const LOCALES: Record<LanguageCode, typeof en> = { en, es };

export const AVAILABLE_LANGUAGES: { code: LanguageCode; label: string }[] = [
  { code: "en", label: "English" },
  { code: "es", label: "Español" },
];

interface I18nContextValue {
  lang: LanguageCode;
  setLang: (lang: LanguageCode) => void;
  t: (path: string) => string;
}

const I18nContext = createContext<I18nContextValue>({
  lang: "en",
  setLang: () => {},
  t: (p) => p,
});

export function I18nProvider({
  lang,
  setLang,
  children,
}: {
  lang: LanguageCode;
  setLang: (lang: LanguageCode) => void;
  children: React.ReactNode;
}) {
  const dict = LOCALES[lang] ?? en;

  const t = (path: string): string => {
    const parts = path.split(".");
    let cur: unknown = dict;
    for (const part of parts) {
      if (cur && typeof cur === "object" && part in cur) {
        cur = (cur as Record<string, unknown>)[part];
      } else {
        return path;
      }
    }
    return typeof cur === "string" ? cur : path;
  };

  return React.createElement(
    I18nContext.Provider,
    { value: { lang, setLang, t } },
    children
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
