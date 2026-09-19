import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, type Role } from "../api";

interface RolePreset {
  id: string;
  role: Role;
  label: string;
  username: string;
  password: string;
  description: string;
  scope: string;
}

const PRIMARY_PRESETS: RolePreset[] = [
  {
    id: "admin",
    role: "admin",
    label: "Admin",
    username: "admin",
    password: "admin123",
    description: "Full system administration, user management, site-scoping & model governance",
    scope: "Org-Wide (All Sites)",
  },
  {
    id: "analyst",
    role: "analyst",
    label: "HSE Analyst",
    username: "analyst",
    password: "analyst123",
    description: "Daily triage queue, AI classification confirm/override & LSR tag adjustment",
    scope: "Duliajan GCS & Digboi Refinery",
  },
  {
    id: "manager",
    role: "site_manager",
    label: "Site Manager",
    username: "manager",
    password: "manager123",
    description: "Site-scoped SIF-density rankings, precursor clusters & corrective action items",
    scope: "Duliajan GCS",
  },
  {
    id: "leadership",
    role: "leadership",
    label: "Leadership",
    username: "leadership",
    password: "leader123",
    description: "Org-wide risk overview, LSR distribution, trend analytics & executive focus areas",
    scope: "Org-Wide (Read-Only)",
  },
];

const SITE_ACCOUNTS: RolePreset[] = [
  {
    id: "manager_digboi",
    role: "site_manager",
    label: "Site Manager — Digboi",
    username: "manager_digboi",
    password: "manager123",
    description: "Site HSE management for Digboi Refinery Area",
    scope: "Digboi Refinery Area",
  },
  {
    id: "manager_moran",
    role: "site_manager",
    label: "Site Manager — Moran",
    username: "manager_moran",
    password: "manager123",
    description: "Site HSE management for Moran Field",
    scope: "Moran Field",
  },
  {
    id: "manager_jorhat",
    role: "site_manager",
    label: "Site Manager — Jorhat",
    username: "manager_jorhat",
    password: "manager123",
    description: "Site HSE management for Jorhat Asset",
    scope: "Jorhat Asset",
  },
  {
    id: "manager_baghjan",
    role: "site_manager",
    label: "Site Manager — Baghjan",
    username: "manager_baghjan",
    password: "manager123",
    description: "Site HSE management for Baghjan Field",
    scope: "Baghjan Field",
  },
  {
    id: "analyst_field",
    role: "analyst",
    label: "Field Analyst — Multi-Asset",
    username: "analyst_field",
    password: "analyst123",
    description: "Field triage and incident reviews for remote assets",
    scope: "Moran, Jorhat & Baghjan",
  },
  {
    id: "admin_sec",
    role: "admin",
    label: "Security & Compliance Admin",
    username: "admin_sec",
    password: "admin123",
    description: "Security compliance, audit verification & access management",
    scope: "Org-Wide",
  },
];

export function LoginPage() {
  const [username, setUsername] = useState("analyst");
  const [password, setPassword] = useState("analyst123");
  const [selectedPreset, setSelectedPreset] = useState<string>("analyst");
  const [showMoreAccounts, setShowMoreAccounts] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  function selectPreset(preset: RolePreset) {
    setSelectedPreset(preset.id);
    setUsername(preset.username);
    setPassword(preset.password);
    setError("");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const session = await login(username, password);
      if (session.role === "admin") {
        navigate("/admin");
      } else if (session.role === "analyst") {
        navigate("/triage");
      } else {
        navigate("/");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed. Please verify credentials.");
    } finally {
      setLoading(false);
    }
  }

  const activePreset =
    PRIMARY_PRESETS.find((p) => p.id === selectedPreset) ||
    SITE_ACCOUNTS.find((p) => p.id === selectedPreset);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4 sm:p-6 font-sans">
      <div className="w-full max-w-xl rounded-xl border border-slate-200 bg-white p-6 sm:p-8 shadow-xl">
        {/* Header Branding */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold text-lg shadow-sm">
              OIL
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Oil India Limited · HSSE</div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">SIF Sentinel</h1>
            </div>
          </div>
          <span className="hidden sm:inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 border border-emerald-200">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 mr-1.5 animate-pulse"></span>
            RBAC Auth v1.0
          </span>
        </div>

        <p className="mt-3 text-xs sm:text-sm text-slate-600">
          Sign in to review fatal-potential precursors, manage safety compliance, and administer role-scoped access.
        </p>

        {/* Role Quick Switcher */}
        <div className="mt-5">
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
            Select Role / Quick Sign-In
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {PRIMARY_PRESETS.map((preset) => {
              const isSelected = selectedPreset === preset.id;
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => selectPreset(preset)}
                  className={`flex flex-col items-center justify-center rounded-lg border p-2.5 text-xs font-medium transition text-center ${
                    isSelected
                      ? "border-indigo-600 bg-indigo-50/70 text-indigo-900 font-semibold shadow-xs"
                      : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <span>{preset.label}</span>
                  <span className="mt-0.5 font-mono text-[10px] text-slate-500">{preset.username}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Expandable Site-Specific Accounts */}
        <div className="mt-2.5">
          <button
            type="button"
            onClick={() => setShowMoreAccounts(!showMoreAccounts)}
            className="flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-800 transition"
          >
            <span>{showMoreAccounts ? "▲ Hide specific operating asset accounts" : "▼ More accounts (Digboi, Moran, Jorhat, Baghjan, Field Analyst)"}</span>
          </button>

          {showMoreAccounts && (
            <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2 rounded-lg border border-slate-200 bg-slate-50/60 p-2.5">
              {SITE_ACCOUNTS.map((preset) => {
                const isSelected = selectedPreset === preset.id;
                return (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => selectPreset(preset)}
                    className={`flex items-center justify-between rounded-md border px-3 py-2 text-left text-xs transition ${
                      isSelected
                        ? "border-indigo-600 bg-indigo-50 text-indigo-900 font-semibold"
                        : "border-slate-200 bg-white text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    <div>
                      <div className="font-medium">{preset.label}</div>
                      <div className="text-[10px] text-slate-500">{preset.scope}</div>
                    </div>
                    <span className="font-mono text-[11px] text-slate-400">{preset.username}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected Role Scope & Capabilities Badge */}
        {activePreset && (
          <div className="mt-4 rounded-lg bg-slate-50 border border-slate-200 p-3 text-xs text-slate-600">
            <div className="flex items-center justify-between font-medium text-slate-800">
              <span className="capitalize font-semibold text-slate-900">
                {activePreset.role.replace("_", " ")} Access
              </span>
              <span className="rounded bg-slate-200 px-2 py-0.5 text-[10px] font-mono text-slate-700">
                Scope: {activePreset.scope}
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-600 leading-relaxed">{activePreset.description}</p>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={onSubmit} className="mt-4 space-y-3.5">
          <div>
            <label className="block text-xs font-semibold text-slate-700">
              Username
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-indigo-600 focus:ring-2 focus:ring-indigo-100"
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                  setSelectedPreset("");
                }}
                required
              />
            </label>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700">
              Password
              <input
                type="password"
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-indigo-600 focus:ring-2 focus:ring-indigo-100"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs font-medium text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <span className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin"></span>
                <span>Signing in...</span>
              </>
            ) : (
              <span>Sign in</span>
            )}
          </button>
        </form>

        {/* Footer Note */}
        <div className="mt-5 border-t border-slate-100 pt-3 text-center text-[11px] text-slate-500">
          <span>Complies with OIL HSSE Security & Access Policy · Role-Based Scoped Access</span>
        </div>
      </div>
    </div>
  );
}
