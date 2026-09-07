import React, { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { clearSession, getStoredUser, type Role } from "../api";

const NAV: Array<{ to: string; label: string; icon: React.ReactNode; roles: Role[] }> = [
  {
    to: "/",
    label: "Dashboard",
    icon: (
      <svg className="w-4 h-4 opacity-80" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 13h4v8H3v-8zm7-8h4v16h-4V5zm7 5h4v11h-4V10z" />
      </svg>
    ),
    roles: ["analyst", "site_manager", "leadership", "admin"],
  },
  {
    to: "/triage",
    label: "Triage Queue",
    icon: (
      <svg className="w-4 h-4 opacity-80" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
      </svg>
    ),
    roles: ["analyst", "site_manager", "leadership"],
  },
  {
    to: "/clusters",
    label: "Cluster Explorer",
    icon: (
      <svg className="w-4 h-4 opacity-80" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
      </svg>
    ),
    roles: ["analyst", "site_manager", "leadership", "admin"],
  },
  {
    to: "/ingestion",
    label: "Data Ingestion",
    icon: (
      <svg className="w-4 h-4 opacity-80" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
      </svg>
    ),
    roles: ["analyst", "site_manager", "admin"],
  },
  {
    to: "/admin",
    label: "Admin & Model",
    icon: (
      <svg className="w-4 h-4 opacity-80" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    roles: ["admin"],
  },
];

export function Layout() {
  const user = getStoredUser();
  const navigate = useNavigate();
  const role = user?.role;
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-slate-100 font-sans text-ink">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[240px] flex-col bg-soot text-white transition-transform duration-200 lg:static lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="border-b border-white/10 px-5 py-5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-ash">Oil India Limited</span>
          </div>
          <div className="mt-2 flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan/20 border border-cyan/40 text-cyan">
              <svg className="w-5 h-5 text-cyan" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <div className="text-[15px] font-bold tracking-tight text-white leading-tight">SIF Sentinel</div>
              <div className="text-[10px] text-ash tracking-wide">Enterprise HSE Intelligence</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 py-4 space-y-1">
          {NAV.filter((item) => !role || item.roles.includes(role)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 border-l-[3px] px-5 py-2.5 text-[13px] font-medium transition ${
                  isActive
                    ? "border-cyan bg-white/10 text-white font-semibold"
                    : "border-transparent text-ash hover:bg-white/5 hover:text-white"
                }`
              }
            >
              <span className="flex items-center justify-center">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* User Profile & Sign Out */}
        <div className="border-t border-white/10 px-5 py-4 text-[12px] text-ash">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-semibold text-white truncate max-w-[140px]">{user?.username || "HSE Analyst"}</div>
              <div className="text-[10px] text-ash/80 capitalize">{user?.role?.replace("_", " ") || "Analyst"}</div>
            </div>
            <button
              className="rounded border border-white/20 px-2 py-1 text-[11px] text-ash hover:border-white hover:text-white transition"
              onClick={() => {
                clearSession();
                navigate("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Top Header Bar */}
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-white px-6 shadow-xs">
          <div className="flex items-center gap-3">
            <button
              className="lg:hidden rounded p-1 text-warm hover:bg-slate-100"
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label="Toggle navigation menu"
            >
              ☰
            </button>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-ink">SIH Smart Automation — SIF Precursor Detection & Prevention</span>
              <span className="hidden sm:inline-block rounded bg-indigo-50 border border-indigo-200 px-2 py-0.5 text-[10px] font-mono font-semibold text-indigo-700">
                IOGP 12 LSR Engine v1.0
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs">
            <div className="hidden md:flex items-center gap-1.5 text-warm">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <span>System Status: <strong className="text-emerald-700 font-medium">Operational</strong></span>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="min-w-0 flex-1 p-6 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
