import {
  ActionIcon,
  AppShell,
  Avatar,
  Badge,
  Box,
  Burger,
  Divider,
  Group,
  Menu,
  NavLink,
  Paper,
  Stack,
  Text,
  Tooltip,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, LogOut, User, Building2, MoonStar, SunMedium } from "lucide-react";
import { useEffect } from "react";
import { Link, NavLink as RouterNavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import logoMark from "../assets/logo-mark.svg";
import turingEdgeLogo from "../assets/turingedge-logo.png";
import { apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { canShowNavItem, NAV_ITEMS } from "./nav";
import type { BuildInfo } from "../types/api";

function toTitle(slug: string): string {
  if (!slug) return "Overview";
  return slug
    .replace(/-/g, " ")
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function AppShellLayout() {
  const [opened, { toggle }] = useDisclosure(false);
  const { user, role, permissions, logout } = useAuth();
  const { setColorScheme } = useMantineColorScheme({ keepTransitions: false });
  const computedColorScheme = useComputedColorScheme("light");
  const isDark = computedColorScheme === "dark";
  const location = useLocation();
  const navigate = useNavigate();
  const isCallingRoute = location.pathname.startsWith("/app/calling");

  const buildQuery = useQuery({
    queryKey: ["build_info"],
    queryFn: () => apiFetch<BuildInfo>("/api/system/build_info"),
    staleTime: 15_000,
  });

  const crumbs = location.pathname
    .split("/")
    .filter(Boolean)
    .map((segment, index, segments) => {
      const to = `/${segments.slice(0, index + 1).join("/")}`;
      return (
        <Link key={to} to={to} style={{ textDecoration: "none", color: "var(--te-shell-crumb)" }}>
          {toTitle(segment)}
        </Link>
      );
    });

  const navItems = NAV_ITEMS.filter((item) =>
    canShowNavItem({
      item,
      permissions,
      role,
      pilotMode: !!buildQuery.data?.pilot_mode,
    })
  );

  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const coarsePointer = window.matchMedia("(pointer: coarse)").matches;
    if (reducedMotion || coarsePointer) {
      return;
    }
    let raf = 0;
    const root = document.documentElement;
    const handleMove = (event: MouseEvent) => {
      const nx = event.clientX / Math.max(window.innerWidth, 1) - 0.5;
      const ny = event.clientY / Math.max(window.innerHeight, 1) - 0.5;
      const px = nx * 34;
      const py = ny * 24;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        root.style.setProperty("--te-parallax-x", `${px}px`);
        root.style.setProperty("--te-parallax-y", `${py}px`);
      });
    };
    window.addEventListener("mousemove", handleMove, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("mousemove", handleMove);
      root.style.setProperty("--te-parallax-x", "0px");
      root.style.setProperty("--te-parallax-y", "0px");
    };
  }, []);

  useEffect(() => {
    if (opened) {
      toggle();
    }
    // Close mobile nav when route changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const shellMainBackground = "var(--te-shell-main-bg)";
  const shellHeaderBackground = "var(--te-shell-header-bg)";
  const shellNavbarBackground = "var(--te-shell-navbar-bg)";
  const shellHeaderBorder = "1px solid var(--te-shell-header-border)";
  const shellNavbarBorder = "1px solid var(--te-shell-navbar-border)";
  const shellSurface = "var(--te-shell-surface)";
  const shellChromeBorder = "1px solid var(--te-shell-chip-border)";

  return (
    <AppShell
      header={{ height: 82 }}
      navbar={{ width: isCallingRoute ? 288 : 306, breakpoint: "md", collapsed: { mobile: !opened } }}
      padding={isCallingRoute ? "md" : "lg"}
      styles={{
        main: {
          background: shellMainBackground,
          paddingTop: isCallingRoute ? 90 : 94,
        },
      }}
    >
      <AppShell.Header
        px="md"
        py="xs"
        style={{
          borderBottom: shellHeaderBorder,
          background: shellHeaderBackground,
          backdropFilter: "blur(20px) saturate(138%)",
          boxShadow: "var(--te-shell-shadow)",
        }}
      >
        <Group justify="space-between" align="center" h="100%" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="md" size="sm" color="var(--te-shell-burger)" />
            <img src={logoMark} alt="Recovery OS" width={36} height={36} style={{ borderRadius: 11, boxShadow: "var(--te-shell-mark-shadow)" }} />
            <Stack gap={0}>
              <Group gap={6} align="center">
                <Text fw={800} size="md" c="var(--te-shell-title)" style={{ letterSpacing: "-0.01em" }}>NBFC Recovery OS</Text>
                <Badge variant="filled" color="blue" radius="sm" style={{ boxShadow: "0 6px 18px rgba(18, 93, 255, 0.3)" }}>
                  Ops Floor
                </Badge>
              </Group>
              <Group gap={8} align="center">
                <Building2 size={13} color="var(--te-shell-copy)" />
                <Text size="xs" c="var(--te-shell-copy)">TuringEdge Demo Org</Text>
                <Text size="xs" c="var(--te-shell-muted)">•</Text>
                <Text size="xs" c="var(--te-shell-copy)">{crumbs.length ? crumbs[crumbs.length - 1] : "Overview"}</Text>
              </Group>
            </Stack>
          </Group>

          <Group gap={8} wrap="nowrap">
            {buildQuery.data?.demo_mode ? (
              <Badge variant="light" color="teal" radius="sm">DEMO</Badge>
            ) : null}
            {buildQuery.data?.pilot_mode ? (
              <Badge variant="light" color="orange" radius="sm">PILOT</Badge>
            ) : null}
            <Tooltip label={isDark ? "Switch to light mode" : "Switch to dark mode"}>
              <ActionIcon
                variant="default"
                radius="xl"
                size="lg"
                onClick={() => setColorScheme(isDark ? "light" : "dark")}
                aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
                style={{
                  border: shellChromeBorder,
                  background: "var(--te-shell-chip-bg)",
                  boxShadow: "var(--te-shell-chip-shadow)",
                  color: "var(--te-shell-title)",
                }}
              >
                {isDark ? <SunMedium size={16} /> : <MoonStar size={16} />}
              </ActionIcon>
            </Tooltip>
            <Badge variant="outline" color="blue" radius="sm" style={{ color: "var(--te-shell-badge-copy)", borderColor: "var(--te-shell-badge-border)" }}>
              BUILD {String(buildQuery.data?.static_token || "-").toUpperCase()}
            </Badge>
            <Menu shadow="md" width={250} position="bottom-end">
              <Menu.Target>
                <UnstyledButton>
                  <Group
                    gap="xs"
                    wrap="nowrap"
                    style={{
                      padding: "6px 10px",
                      borderRadius: 999,
                      border: shellChromeBorder,
                      background: "var(--te-shell-chip-bg)",
                      boxShadow: "var(--te-shell-chip-shadow)",
                    }}
                  >
                    <Avatar radius="xl" color="blue" variant="light" size="sm">
                      {(user?.full_name || user?.username || "U").slice(0, 1).toUpperCase()}
                    </Avatar>
                    <Box>
                      <Text size="xs" fw={600} lh={1.1} c="var(--te-shell-title)">{user?.full_name || user?.username || "User"}</Text>
                      <Text size="10px" c="var(--te-shell-muted)" lh={1.1}>{role || "-"}</Text>
                    </Box>
                    <ChevronDown size={14} color="var(--te-shell-muted)" />
                  </Group>
                </UnstyledButton>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<User size={14} />} onClick={() => navigate("/app/profile")}>Profile</Menu.Item>
                <Menu.Item
                  leftSection={<LogOut size={14} />}
                  onClick={async () => {
                    await logout();
                    navigate("/login", { replace: true });
                  }}
                >
                  Logout
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar
        p="sm"
        className="te-subtle-scroll"
        style={{
          borderRight: shellNavbarBorder,
          background: shellNavbarBackground,
          backdropFilter: "blur(20px) saturate(134%)",
          boxShadow: "var(--te-shell-navbar-shadow)",
        }}
      >
        <Stack h="100%" justify="space-between">
          <Stack gap="sm">
            <Paper radius="md" p="sm" withBorder style={{ borderColor: "var(--te-shell-navbar-border)", background: shellSurface }}>
              <Stack gap={8}>
                <img
                  src={turingEdgeLogo}
                  alt="TuringEdge"
                  style={{ width: "100%", maxWidth: 186, objectFit: "contain", filter: "var(--te-shell-wordmark-filter)" }}
                />
                <Text size="11px" c="var(--te-shell-muted)" fw={600} tt="uppercase" style={{ letterSpacing: "0.09em" }}>
                  TuringEdge Command
                </Text>
              </Stack>
            </Paper>
            <Divider color="var(--te-shell-navbar-border)" />
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  component={RouterNavLink}
                  to={item.to}
                  label={item.label}
                  leftSection={<Icon size={16} strokeWidth={2} />}
                  active={location.pathname === item.to || location.pathname.startsWith(item.to + "/")}
                  styles={{
                    root: {
                      borderRadius: 12,
                      color: "var(--te-shell-nav)",
                      border: "1px solid var(--te-shell-nav-border)",
                      background: "var(--te-shell-nav-bg)",
                      "&:hover": {
                        borderColor: "var(--te-shell-nav-hover-border)",
                        background: "var(--te-shell-nav-hover-bg)",
                      },
                    },
                    section: {
                      color: "var(--te-shell-nav-icon)",
                    },
                    label: {
                      fontWeight: 600,
                    },
                  }}
                  style={
                    location.pathname === item.to || location.pathname.startsWith(item.to + "/")
                      ? {
                          background: "var(--te-shell-nav-active-bg)",
                          borderColor: "var(--te-shell-nav-active-border)",
                          boxShadow: "var(--te-shell-nav-active-shadow)",
                        }
                      : undefined
                  }
                  end={item.to === "/app/dashboard"}
                />
              );
            })}
          </Stack>
          <Text size="xs" c="var(--te-shell-muted)" px="xs">
            Recovery OS v1 | Build {buildQuery.data?.static_token || "-"}
          </Text>
        </Stack>
      </AppShell.Navbar>

      <AppShell.Main>
        <Box className="te-main-canvas">
          <Box className="te-parallax-orb te-parallax-orb--one" />
          <Box className="te-parallax-orb te-parallax-orb--two" />
          <Box className="te-main-content">
            <Outlet />
          </Box>
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}
