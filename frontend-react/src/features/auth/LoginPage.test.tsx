import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { LoginPage } from "./LoginPage";

const loginMock = vi.fn(async () => undefined);
const navigateMock = vi.fn();

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ login: loginMock }),
}));

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    apiFetch: vi.fn(async () => ({ demo_mode: true })),
  };
});

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useSearchParams: () => [new URLSearchParams()],
  };
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

describe("LoginPage", () => {
  it("submits credentials and calls login", async () => {
    renderPage();
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "admin123" } });
    fireEvent.click(screen.getByRole("button", { name: /login to recovery os/i }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith("admin", "admin123");
      expect(navigateMock).toHaveBeenCalled();
    });
  });
});
