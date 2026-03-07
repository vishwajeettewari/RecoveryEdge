import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { RequireRole } from "./RequireRole";

vi.mock("./AuthProvider", () => ({
  useAuth: () => ({ role: "CEO" }),
}));

describe("RequireRole", () => {
  it("blocks route when role is not allowed", () => {
    render(
      <MemoryRouter>
        <RequireRole allowed={["ADMIN"]}>
          <div>secret</div>
        </RequireRole>
      </MemoryRouter>
    );
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("allows route when role matches", () => {
    render(
      <MemoryRouter>
        <RequireRole allowed={["CEO", "ADMIN"]}>
          <div>visible</div>
        </RequireRole>
      </MemoryRouter>
    );
    expect(screen.getByText("visible")).toBeInTheDocument();
  });
});
