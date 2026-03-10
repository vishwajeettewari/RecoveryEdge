import { createTheme } from "@mantine/core";

import { tokens } from "./tokens";

export const appTheme = createTheme({
  fontFamily: "SF Pro Display, SF Pro Text, Manrope, Inter, system-ui, -apple-system, Segoe UI, sans-serif",
  primaryColor: "blue",
  defaultRadius: "lg",
  radius: {
    xs: tokens.radii.xs,
    sm: tokens.radii.sm,
    md: tokens.radii.md,
    lg: tokens.radii.lg,
    xl: tokens.radii.xl,
  },
  colors: {
    blue: [
      "#e8f0ff",
      "#d2e2ff",
      "#a8c7ff",
      "#7eadff",
      "#4f8dff",
      "#2f75ff",
      "#125dff",
      "#064ddf",
      "#003eb8",
      "#012f8a",
    ],
    teal: [
      "#e6faf6",
      "#c1f2e7",
      "#8ae5d0",
      "#54d7b8",
      "#25c8a3",
      "#0ab08b",
      "#059474",
      "#03765d",
      "#015847",
      "#003c31",
    ],
  },
  components: {
    AppShell: {
      styles: () => ({
        main: {
          color: "var(--te-component-text)",
        },
      }),
    },
    Card: {
      defaultProps: {
        withBorder: true,
        radius: "lg",
      },
      styles: () => ({
        root: {
          borderColor: "var(--te-component-border)",
          backgroundColor: "var(--te-component-surface)",
          boxShadow: "var(--te-component-shadow)",
          backdropFilter: "blur(18px) saturate(125%)",
          color: "var(--te-component-text)",
        },
      }),
    },
    NavLink: {
      styles: {
        root: {
          borderRadius: tokens.radii.md,
          transition: "all 160ms ease",
        },
      },
    },
    Button: {
      defaultProps: {
        radius: "lg",
      },
      styles: {
        root: {
          fontWeight: 600,
          letterSpacing: "0.005em",
          borderRadius: tokens.radii.lg,
          transition: "transform 160ms ease, box-shadow 180ms ease, filter 180ms ease",
        },
        label: {
          position: "relative",
          zIndex: 2,
        },
      },
    },
    Stepper: {
      styles: () => ({
        stepLabel: {
          fontSize: "0.84rem",
          fontWeight: 600,
          letterSpacing: "0.01em",
          color: "var(--te-component-text)",
        },
        stepDescription: {
          fontSize: "0.72rem",
          color: "var(--te-copy)",
        },
      }),
    },
    TextInput: {
      styles: () => ({
        input: {
          borderColor: "var(--te-input-border)",
          backgroundColor: "var(--te-input-bg)",
          color: "var(--te-input-text)",
        },
      }),
    },
    PasswordInput: {
      styles: () => ({
        input: {
          borderColor: "var(--te-input-border)",
          backgroundColor: "var(--te-input-bg)",
          color: "var(--te-input-text)",
        },
      }),
    },
    Select: {
      styles: () => ({
        input: {
          borderColor: "var(--te-input-border)",
          backgroundColor: "var(--te-input-bg)",
          color: "var(--te-input-text)",
        },
      }),
    },
    JsonInput: {
      styles: () => ({
        input: {
          borderColor: "var(--te-input-border)",
          backgroundColor: "var(--te-input-bg)",
          color: "var(--te-input-text)",
        },
      }),
    },
    Paper: {
      styles: () => ({
        root: {
          borderColor: "var(--te-component-border)",
          backdropFilter: "blur(16px) saturate(120%)",
          color: "var(--te-component-text)",
        },
      }),
    },
    Drawer: {
      styles: () => ({
        content: {
          background: "var(--te-drawer-bg)",
        },
      }),
    },
    Badge: {
      styles: {
        root: {
          fontWeight: 700,
          letterSpacing: "0.02em",
        },
      },
    },
    Table: {
      defaultProps: {
        striped: true,
        highlightOnHover: true,
        horizontalSpacing: "md",
        verticalSpacing: "sm",
        stickyHeader: true,
      },
      styles: () => ({
        th: {
          fontSize: "0.76rem",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "var(--te-table-head-text)",
          fontWeight: 700,
          background: "var(--te-table-head-bg)",
          borderBottom: "1px solid var(--te-table-head-border)",
        },
        td: {
          borderBottom: "1px solid var(--te-table-cell-border)",
          color: "var(--te-table-cell-text)",
          fontSize: "0.85rem",
          verticalAlign: "top",
        },
      }),
    },
    Tabs: {
      styles: () => ({
        list: {
          borderBottom: "1px solid var(--te-tabs-list-border)",
          gap: 6,
        },
        tab: {
          borderTopLeftRadius: 10,
          borderTopRightRadius: 10,
          fontWeight: 600,
          color: "var(--te-tabs-text)",
          "&[data-active]": {
            color: "var(--te-tabs-active-text)",
            background: "var(--te-tabs-active-bg)",
            borderColor: "var(--te-tabs-active-border)",
          },
        },
      }),
    },
    Modal: {
      styles: () => ({
        content: {
          background: "var(--te-modal-bg)",
        },
        header: {
          background: "transparent",
          borderBottom: "1px solid var(--te-modal-header-border)",
        },
      }),
    },
  },
});
