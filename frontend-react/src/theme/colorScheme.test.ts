import { describe, expect, it } from "vitest";

import {
  COLOR_SCHEME_STORAGE_KEY,
  DEFAULT_COLOR_SCHEME,
  explicitColorSchemeManager,
  normalizeColorScheme,
  persistColorScheme,
  readStoredColorScheme,
} from "./colorScheme";

describe("colorScheme", () => {
  it("normalizes unsupported values to the explicit fallback", () => {
    expect(normalizeColorScheme("dark")).toBe("dark");
    expect(normalizeColorScheme("light")).toBe("light");
    expect(normalizeColorScheme("auto")).toBe(DEFAULT_COLOR_SCHEME);
    expect(normalizeColorScheme("unexpected", "dark")).toBe("dark");
  });

  it("persists only explicit light or dark values", () => {
    localStorage.clear();

    expect(persistColorScheme("dark")).toBe("dark");
    expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe("dark");

    expect(persistColorScheme("auto")).toBe(DEFAULT_COLOR_SCHEME);
    expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe(DEFAULT_COLOR_SCHEME);
  });

  it("manager reads invalid or auto storage entries as the explicit fallback", () => {
    localStorage.clear();
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, "auto");
    expect(readStoredColorScheme()).toBe(DEFAULT_COLOR_SCHEME);
    expect(explicitColorSchemeManager.get("dark")).toBe(DEFAULT_COLOR_SCHEME);

    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, "dark");
    expect(explicitColorSchemeManager.get("light")).toBe("dark");
  });
});
