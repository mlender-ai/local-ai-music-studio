import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import en from "./locales/en.json";
import ko from "./locales/ko.json";

export type Locale = "ko" | "en";
export type TranslationKey = keyof typeof ko;

const LOCALE_STORAGE_KEY = "ai_native_daw_locale_v1";
const CATALOGS: Record<Locale, Record<string, string>> = { ko, en };

export function loadSavedLocale(): Locale {
  try {
    const val = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (val === "en" || val === "ko") return val;
  } catch {
    // ignore
  }
  return "ko";
}

export function translate(
  locale: Locale,
  key: TranslationKey,
  vars?: Record<string, string | number>
): string {
  let text = CATALOGS[locale][key] ?? CATALOGS.ko[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.replaceAll(`{${k}}`, String(v));
    }
  }
  return text;
}

/** True when Korean/CJK IME composition is active (must suppress Enter/Space/Delete shortcuts). */
export function isImeComposing(e: KeyboardEvent | React.KeyboardEvent): boolean {
  const native = "nativeEvent" in e ? e.nativeEvent : e;
  return Boolean(native.isComposing || (native as KeyboardEvent).keyCode === 229);
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (loc: Locale) => void;
  toggleLocale: () => void;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => loadSavedLocale());

  const setLocale = useCallback((loc: Locale) => {
    setLocaleState(loc);
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, loc);
    } catch {
      // ignore
    }
  }, []);

  const toggleLocale = useCallback(() => {
    setLocale(locale === "ko" ? "en" : "ko");
  }, [locale, setLocale]);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => translate(locale, key, vars),
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, toggleLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
