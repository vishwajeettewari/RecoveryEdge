import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { CommandCenterPage } from "./CommandCenterPage";

vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) => (
      <div style={{ width: 960, height: 320 }}>{children}</div>
    ),
  };
});

function renderPage() {
  return render(
    <MantineProvider>
      <CommandCenterPage />
    </MantineProvider>
  );
}

describe("CommandCenterPage", () => {
  it("renders the major command center sections and uses theme-bound panel surfaces", () => {
    const { container } = renderPage();

    expect(screen.getByText("AI Collections Command Center")).toBeInTheDocument();
    expect(screen.getByText("Portfolio Health Overview")).toBeInTheDocument();
    expect(screen.getByText("Delinquency & Risk Intelligence")).toBeInTheDocument();
    expect(screen.getByText("Recovery Performance")).toBeInTheDocument();
    expect(screen.getByText("Collections Operations Monitoring")).toBeInTheDocument();
    expect(screen.getByText("AI Decision Intelligence")).toBeInTheDocument();
    expect(screen.getByText("Action & Intervention Panel")).toBeInTheDocument();

    expect(container.querySelectorAll(".te-command-section")).toHaveLength(6);
    expect(container.querySelectorAll(".te-command-chart-card").length).toBeGreaterThanOrEqual(10);

    const forecastPanel = screen.getByText("Next 30 Days").closest(".mantine-Paper-root");
    expect(forecastPanel).not.toBeNull();
    expect(forecastPanel).toHaveStyle({
      background: "var(--te-command-subtle-surface)",
      border: "1px solid var(--te-command-subtle-border)",
    });
  });
});
