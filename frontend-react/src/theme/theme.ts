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
      styles: {
        main: {
          color: tokens.colors.text,
        },
      },
    },
    Card: {
      defaultProps: {
        withBorder: true,
        radius: "lg",
      },
      styles: {
        root: {
          borderColor: tokens.colors.border,
          backgroundColor: tokens.colors.surface,
          boxShadow: tokens.shadows.soft,
          backdropFilter: "blur(18px) saturate(125%)",
        },
      },
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
        radius: "xl",
      },
      styles: {
        root: {
          fontWeight: 700,
          letterSpacing: "0.01em",
          borderRadius: 999,
          transition: "transform 160ms ease, box-shadow 180ms ease, filter 180ms ease",
        },
        label: {
          position: "relative",
          zIndex: 2,
        },
      },
    },
    TextInput: {
      styles: {
        input: {
          borderColor: tokens.colors.border,
          backgroundColor: "#f8fbff",
        },
      },
    },
    PasswordInput: {
      styles: {
        input: {
          borderColor: tokens.colors.border,
          backgroundColor: "#f8fbff",
        },
      },
    },
    Select: {
      styles: {
        input: {
          borderColor: tokens.colors.border,
          backgroundColor: "#f8fbff",
        },
      },
    },
    JsonInput: {
      styles: {
        input: {
          borderColor: tokens.colors.border,
          backgroundColor: "#f8fbff",
        },
      },
    },
    Paper: {
      styles: {
        root: {
          borderColor: tokens.colors.border,
          backdropFilter: "blur(16px) saturate(120%)",
        },
      },
    },
    Drawer: {
      styles: {
        content: {
          background:
            "radial-gradient(600px 220px at 100% 0%, rgba(30,100,255,0.12), transparent 50%), #f7faff",
        },
      },
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
      styles: {
        th: {
          fontSize: "0.76rem",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "#556074",
          fontWeight: 700,
          background: "rgba(244, 248, 255, 0.94)",
          borderBottom: "1px solid rgba(19, 28, 45, 0.1)",
        },
        td: {
          borderBottom: "1px solid rgba(19, 28, 45, 0.07)",
          color: "#1b2330",
          fontSize: "0.85rem",
          verticalAlign: "top",
        },
      },
    },
    Tabs: {
      styles: {
        list: {
          borderBottom: "1px solid rgba(19, 28, 45, 0.1)",
          gap: 6,
        },
        tab: {
          borderTopLeftRadius: 10,
          borderTopRightRadius: 10,
          fontWeight: 600,
          color: "#536079",
          "&[data-active]": {
            color: "#0e2145",
            background: "linear-gradient(180deg, rgba(18, 93, 255, 0.13), rgba(18, 93, 255, 0.04))",
            borderColor: "rgba(18, 93, 255, 0.34)",
          },
        },
      },
    },
    Modal: {
      styles: {
        content: {
          background:
            "radial-gradient(480px 180px at 100% 0%, rgba(18, 93, 255, 0.12), transparent 55%), #f8fbff",
        },
        header: {
          background: "transparent",
          borderBottom: "1px solid rgba(19, 28, 45, 0.08)",
        },
      },
    },
  },
});
