import {
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
  UnstyledButton,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, LogOut, User, Building2 } from "lucide-react";
import { useEffect } from "react";
import { Link, NavLink as RouterNavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import logoMark from "../assets/logo-mark.svg";
import turingEdgeLogo from "../assets/turingedge-logo.png";
import { apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { canShowNavItem, NAV_ITEMS } from "./nav";
import type { BuildInfo } from "../types/api";
import { tokens } from "../theme/tokens";

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
        <Link key={to} to={to} style={{ textDecoration: "none", color: tokens.colors.primary }}>
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

  return (
    <AppShell
      header={{ height: 82 }}
      navbar={{ width: isCallingRoute ? 288 : 306, breakpoint: "md", collapsed: { mobile: !opened } }}
      padding={isCallingRoute ? "md" : "lg"}
      styles={{
        main: {
          background:
            "radial-gradient(1100px 620px at -6% -12%, rgba(71, 130, 255, 0.18), transparent 48%), radial-gradient(940px 520px at 108% -12%, rgba(0, 181, 153, 0.14), transparent 48%), linear-gradient(180deg, #f7f9fd 0%, #f2f5fb 52%, #edf2f9 100%)",
          paddingTop: isCallingRoute ? 90 : 94,
        },
      }}
    >
      <AppShell.Header
        px="md"
        py="xs"
        style={{
          borderBottom: "1px solid rgba(15, 24, 42, 0.09)",
          background:
            "radial-gradient(560px 220px at -20% 0%, rgba(64, 124, 255, 0.22), transparent 56%), radial-gradient(520px 260px at 120% 0%, rgba(0, 188, 160, 0.16), transparent 56%), linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.72))",
          backdropFilter: "blur(20px) saturate(138%)",
          boxShadow: "0 12px 30px rgba(12, 25, 48, 0.08)",
        }}
      >
        <Group justify="space-between" align="center" h="100%" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="md" size="sm" color="#454b57" />
            <img src={logoMark} alt="Recovery OS" width={36} height={36} style={{ borderRadius: 11, boxShadow: "0 8px 24px rgba(5,18,35,0.4)" }} />
            <Stack gap={0}>
              <Group gap={6} align="center">
                <Text fw={800} size="md" c="#101217" style={{ letterSpacing: "-0.01em" }}>NBFC Recovery OS</Text>
                <Badge variant="filled" color="blue" radius="sm" style={{ boxShadow: "0 6px 18px rgba(18, 93, 255, 0.3)" }}>
                  Ops Floor
                </Badge>
              </Group>
              <Group gap={8} align="center">
                <Building2 size={13} color="#5f6672" />
                <Text size="xs" c="#5f6672">TuringEdge Demo Org</Text>
                <Text size="xs" c="#8b94a4">•</Text>
                <Text size="xs" c="#5f6672">{crumbs.length ? crumbs[crumbs.length - 1] : "Overview"}</Text>
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
            <Badge variant="outline" color="blue" radius="sm" style={{ color: "#2f415f", borderColor: "rgba(0, 113, 227, 0.35)" }}>
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
                      border: "1px solid rgba(17, 27, 45, 0.14)",
                      background: "linear-gradient(180deg, rgba(255, 255, 255, 0.86), rgba(255, 255, 255, 0.74))",
                      boxShadow: "0 8px 22px rgba(12, 25, 48, 0.08)",
                    }}
                  >
                    <Avatar radius="xl" color="blue" variant="light" size="sm">
                      {(user?.full_name || user?.username || "U").slice(0, 1).toUpperCase()}
                    </Avatar>
                    <Box>
                      <Text size="xs" fw={600} lh={1.1} c="#1d1d1f">{user?.full_name || user?.username || "User"}</Text>
                      <Text size="10px" c="#6e6e73" lh={1.1}>{role || "-"}</Text>
                    </Box>
                    <ChevronDown size={14} color="#6e6e73" />
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
          borderRight: "1px solid rgba(15, 24, 42, 0.08)",
          background:
            "radial-gradient(540px 240px at 0% 0%, rgba(34, 104, 255, 0.14), transparent 58%), radial-gradient(500px 240px at 100% 8%, rgba(0, 188, 160, 0.08), transparent 58%), linear-gradient(180deg, rgba(255, 255, 255, 0.78) 0%, rgba(255, 255, 255, 0.62) 52%, rgba(255, 255, 255, 0.72) 100%)",
          backdropFilter: "blur(20px) saturate(134%)",
          boxShadow: "inset -1px 0 0 rgba(90, 106, 140, 0.1)",
        }}
      >
        <Stack h="100%" justify="space-between">
          <Stack gap="sm">
            <Paper radius="md" p="sm" withBorder style={{ borderColor: "rgba(15, 24, 42, 0.1)", background: "rgba(255, 255, 255, 0.62)" }}>
              <Stack gap={8}>
                <img
                  src={turingEdgeLogo}
                  alt="TuringEdge"
                  style={{ width: "100%", maxWidth: 186, objectFit: "contain", filter: "contrast(1.08)" }}
                />
                <Text size="11px" c="#6f7784" fw={600} tt="uppercase" style={{ letterSpacing: "0.09em" }}>
                  TuringEdge Command
                </Text>
              </Stack>
            </Paper>
            <Divider color="rgba(15, 24, 42, 0.1)" />
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
                      color: "#263242",
                      border: "1px solid transparent",
                    },
                    section: {
                      color: "#4f6078",
                    },
                    label: {
                      fontWeight: 600,
                    },
                  }}
                  style={
                    location.pathname === item.to || location.pathname.startsWith(item.to + "/")
                      ? {
                          background:
                            "linear-gradient(90deg, rgba(0, 113, 227, 0.18), rgba(0, 113, 227, 0.08))",
                          borderColor: "rgba(0, 113, 227, 0.4)",
                          boxShadow: "0 10px 20px rgba(17, 32, 57, 0.09)",
                        }
                      : undefined
                  }
                  end={item.to === "/app/dashboard"}
                />
              );
            })}
          </Stack>
          <Text size="xs" c="#6f7784" px="xs">
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
