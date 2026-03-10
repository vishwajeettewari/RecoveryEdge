import type { MantineColorScheme, MantineColorSchemeManager } from "@mantine/core";

export const COLOR_SCHEME_STORAGE_KEY = "te-color-scheme";
export const DEFAULT_COLOR_SCHEME = "light";

export type ExplicitColorScheme = Exclude<MantineColorScheme, "auto">;

function fallbackColorScheme(value?: string | null): ExplicitColorScheme {
  return value === "dark" ? "dark" : "light";
}

export function normalizeColorScheme(value?: string | null, fallback: ExplicitColorScheme = DEFAULT_COLOR_SCHEME): ExplicitColorScheme {
  if (value === "dark" || value === "light") {
    return value;
  }
  return fallbackColorScheme(fallback);
}

export function readStoredColorScheme(
  storage: Pick<Storage, "getItem"> | null | undefined = typeof window === "undefined" ? null : window.localStorage,
  fallback: ExplicitColorScheme = DEFAULT_COLOR_SCHEME
): ExplicitColorScheme {
  if (!storage) {
    return fallbackColorScheme(fallback);
  }
  try {
    return normalizeColorScheme(storage.getItem(COLOR_SCHEME_STORAGE_KEY), fallback);
  } catch {
    return fallbackColorScheme(fallback);
  }
}

export function persistColorScheme(
  value: MantineColorScheme,
  storage: Pick<Storage, "setItem"> | null | undefined = typeof window === "undefined" ? null : window.localStorage,
  fallback: ExplicitColorScheme = DEFAULT_COLOR_SCHEME
): ExplicitColorScheme {
  const normalized = normalizeColorScheme(value, fallback);
  if (!storage) {
    return normalized;
  }
  try {
    storage.setItem(COLOR_SCHEME_STORAGE_KEY, normalized);
  } catch {
    // ignore storage failures; theme still updates in memory
  }
  return normalized;
}

export const explicitColorSchemeManager: MantineColorSchemeManager = (() => {
  let handleStorageEvent: ((event: StorageEvent) => void) | undefined;

  return {
    get: () => readStoredColorScheme(undefined, DEFAULT_COLOR_SCHEME),
    set: (value) => {
      persistColorScheme(value);
    },
    subscribe: (onUpdate) => {
      handleStorageEvent = (event) => {
        if (event.storageArea !== window.localStorage || event.key !== COLOR_SCHEME_STORAGE_KEY) {
          return;
        }
        onUpdate(normalizeColorScheme(event.newValue));
      };
      window.addEventListener("storage", handleStorageEvent);
    },
    unsubscribe: () => {
      if (handleStorageEvent) {
        window.removeEventListener("storage", handleStorageEvent);
      }
    },
    clear: () => {
      persistColorScheme(DEFAULT_COLOR_SCHEME);
    },
  };
})();
