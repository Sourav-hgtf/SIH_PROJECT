import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

const { login } = vi.hoisted(() => ({ login: vi.fn() }));
vi.mock("../api", () => ({ login }));
import { LoginPage } from "./Login";

describe("LoginPage", () => {
  beforeEach(() => login.mockReset());
  it("shows a failed-login error", async () => {
    login.mockRejectedValueOnce(new Error("Invalid credentials"));
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
  });
  it("submits credentials", async () => {
    login.mockResolvedValueOnce({ role: "analyst" });
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(login).toHaveBeenCalledWith("analyst", "analyst123"));
  });
});
