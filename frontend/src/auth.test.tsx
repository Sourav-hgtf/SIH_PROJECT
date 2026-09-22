import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

const { getToken, getStoredUser } = vi.hoisted(() => ({ getToken: vi.fn(), getStoredUser: vi.fn() }));
vi.mock("./api", () => ({ getToken, getStoredUser }));
import { RequireAuth } from "./auth";

describe("RequireAuth", () => {
  it("redirects anonymous users", () => {
    getToken.mockReturnValue(null); getStoredUser.mockReturnValue(null);
    render(<MemoryRouter initialEntries={["/admin"]}><Routes><Route path="/login" element={<p>Login screen</p>} /><Route element={<RequireAuth roles={["admin"]} />}><Route path="/admin" element={<p>Admin screen</p>} /></Route></Routes></MemoryRouter>);
    expect(screen.getByText("Login screen")).toBeInTheDocument();
  });
  it("blocks users without the required role", () => {
    getToken.mockReturnValue("token"); getStoredUser.mockReturnValue({ role: "analyst" });
    render(<MemoryRouter initialEntries={["/admin"]}><Routes><Route path="/" element={<p>Dashboard screen</p>} /><Route element={<RequireAuth roles={["admin"]} />}><Route path="/admin" element={<p>Admin screen</p>} /></Route></Routes></MemoryRouter>);
    expect(screen.getByText("Dashboard screen")).toBeInTheDocument();
  });
});
