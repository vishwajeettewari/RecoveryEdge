export const tokens = {
  colors: {
    canvas: "#f5f5f7",
    surface: "rgba(255, 255, 255, 0.78)",
    elevated: "rgba(255, 255, 255, 0.92)",
    border: "rgba(19, 28, 45, 0.09)",
    text: "#1d1d1f",
    muted: "#6e6e73",
    primary: "#0071e3",
    primarySoft: "rgba(0, 113, 227, 0.12)",
    success: "#1f8f5a",
    warning: "#b87820",
    danger: "#cd3f46",
    info: "#1682d8",
    slate900: "#121315",
    slate800: "#202124",
    slate700: "#303136",
    accent: "#00c7be",
  },
  radii: {
    xs: 8,
    sm: 10,
    md: 14,
    lg: 18,
    xl: 24,
  },
  shadows: {
    card: "0 16px 40px rgba(15, 24, 42, 0.08)",
    soft: "0 8px 22px rgba(15, 24, 42, 0.06)",
    glow: "0 0 0 1px rgba(0, 113, 227, 0.22), 0 24px 44px rgba(14, 23, 40, 0.14)",
  },
  spacing: {
    xxs: 4,
    xs: 8,
    sm: 12,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 40,
  },
};

export type AppTokens = typeof tokens;
