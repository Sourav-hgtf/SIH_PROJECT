import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";

export function LoginPage() {
  const [username, setUsername] = useState("analyst");
  const [password, setPassword] = useState("analyst123");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const session = await login(username, password);
      navigate(session.role === "analyst" ? "/triage" : session.role === "admin" ? "/admin" : "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <form onSubmit={onSubmit} className="w-full max-w-md rounded-[10px] border border-border bg-white p-8 shadow-card">
        <p className="text-[11px] uppercase tracking-wide text-warm">Oil India Limited · HSSE</p>
        <h1 className="mt-2 text-[24px] font-semibold leading-tight">SIF Sentinel</h1>
        <p className="mt-2 text-warm">Sign in to review fatal-potential precursors, not just reported severity.</p>
        <label className="mt-6 block text-[13px] font-medium">
          Username
          <input
            className="mt-1 w-full rounded-[6px] border border-muted bg-white px-3 py-2 outline-none focus:ring-2 focus:ring-cyan"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>
        <label className="mt-4 block text-[13px] font-medium">
          Password
          <input
            type="password"
            className="mt-1 w-full rounded-[6px] border border-muted bg-white px-3 py-2 outline-none focus:ring-2 focus:ring-cyan"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error ? <p className="mt-3 text-[13px] text-risk-critical">{error}</p> : null}
        <button type="submit" className="mt-6 w-full rounded-[8px] bg-cyan px-4 py-2.5 font-medium text-white">
          Sign in
        </button>
        <p className="mt-4 text-[12px] text-warm">
          Demo: analyst / analyst123 · manager / manager123 · leadership / leader123 · admin / admin123
        </p>
      </form>
    </div>
  );
}
