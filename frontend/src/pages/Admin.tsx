import { FormEvent, useEffect, useState } from "react";
import { api, getStoredUser, type ModelEvaluationRecord, type Role } from "../api";

interface UserItem {
  id: string;
  username: string;
  role: Role;
  site_scope: string[];
  is_active: boolean;
  email?: string;
}

interface SiteItem {
  id: string;
  name: string;
  region?: string;
}
import { api, type ModelEvaluationRecord, type Role } from "../api";
import { formatPercent } from "../utils/format";

export function AdminPage() {
  const currentUser = getStoredUser();
  const [users, setUsers] = useState<UserItem[]>([]);
  const [sites, setSites] = useState<SiteItem[]>([]);
  const [audit, setAudit] = useState<Array<{ id: string; action_type: string; entity_type: string; created_at: string; user_id: string | null }>>([]);
  const [trainingRuns, setTrainingRuns] = useState<Array<{ id: string; model_version: string; feedback_count: number; metrics_before: Record<string, number>; metrics_after: Record<string, number>; created_at: string }>>([]);
  const [evaluations, setEvaluations] = useState<ModelEvaluationRecord[]>([]);
  const [evaluationError, setEvaluationError] = useState("");

  // Filters & State
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [trainingMessage, setTrainingMessage] = useState("");

  // Create User Form State
  const [createUsername, setCreateUsername] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createEmail, setCreateEmail] = useState("");
  const [createRole, setCreateRole] = useState<Role>("analyst");
  const [createSiteScope, setCreateSiteScope] = useState<string[]>([]);
  const [createMessage, setCreateMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [createLoading, setCreateLoading] = useState(false);

  // Edit User Modal State
  const [editingUser, setEditingUser] = useState<UserItem | null>(null);
  const [editRole, setEditRole] = useState<Role>("analyst");
  const [editEmail, setEditEmail] = useState("");
  const [editPassword, setEditPassword] = useState("");
  const [editSiteScope, setEditSiteScope] = useState<string[]>([]);
  const [editIsActive, setEditIsActive] = useState(true);
  const [editMessage, setEditMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [editLoading, setEditLoading] = useState(false);

  function load() {
    api.users().then(setUsers).catch(console.error);
    api.sites().then(setSites).catch(console.error);
    api.audit().then(setAudit).catch(console.error);
    api.trainingRuns().then(setTrainingRuns).catch(console.error);
    api.modelEvaluation().then((data) => setEvaluations(data.records)).catch((error) => setEvaluationError(error.message));
  }

  useEffect(() => {
    load();
  }, []);

  async function onRetrain() {
    setTrainingMessage("");
    try {
      const run = await api.createTrainingRun();
      setTrainingMessage(`Deployed ${run.model_version}. Future ingestion will use its calibrated threshold.`);
      load();
    } catch (err) {
      setTrainingMessage(err instanceof Error ? err.message : "Retraining failed.");
    }
  }

  async function handleCreateUser(e: FormEvent) {
    e.preventDefault();
    setCreateMessage(null);
    setCreateLoading(true);
    try {
      await api.createUser({
        username: createUsername.trim(),
        password: createPassword,
        role: createRole,
        site_scope: createRole === "leadership" || createRole === "admin" ? [] : createSiteScope,
        email: createEmail.trim() || undefined,
      });
      setCreateUsername("");
      setCreatePassword("");
      setCreateEmail("");
      setCreateSiteScope([]);
      setCreateRole("analyst");
      setCreateMessage({ type: "success", text: `User '${createUsername}' created successfully.` });
      load();
    } catch (err) {
      setCreateMessage({ type: "error", text: err instanceof Error ? err.message : "Failed to create user." });
    } finally {
      setCreateLoading(false);
    }
  }

  function openEditModal(u: UserItem) {
    setEditingUser(u);
    setEditRole(u.role);
    setEditEmail(u.email || "");
    setEditPassword("");
    setEditSiteScope(u.site_scope || []);
    setEditIsActive(u.is_active);
    setEditMessage(null);
  }

  async function handleSaveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editingUser) return;
    setEditMessage(null);
    setEditLoading(true);
    try {
      await api.updateUser(editingUser.id, {
        role: editRole,
        email: editEmail.trim() || undefined,
        site_scope: editRole === "leadership" || editRole === "admin" ? [] : editSiteScope,
        is_active: editIsActive,
        password: editPassword.trim() ? editPassword.trim() : undefined,
      });
      setEditingUser(null);
      load();
    } catch (err) {
      setEditMessage({ type: "error", text: err instanceof Error ? err.message : "Failed to update user." });
    } finally {
      setEditLoading(false);
    }
  }

  async function handleToggleActive(u: UserItem) {
    try {
      await api.toggleUserActive(u.id, !u.is_active);
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Could not toggle user status");
    }
  }

  async function handleDeleteUser(u: UserItem) {
    if (!window.confirm(`Are you sure you want to delete user '${u.username}'? This action is permanent and logged in the audit trail.`)) {
      return;
    }
    try {
      await api.deleteUser(u.id);
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete user");
    }
  }

  const filteredUsers = users.filter((u) => {
    const matchesSearch =
      u.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (u.email && u.email.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesRole = roleFilter === "all" || u.role === roleFilter;
    return matchesSearch && matchesRole;
  });

  const getRoleBadge = (r: Role) => {
    switch (r) {
      case "admin":
        return <span className="inline-flex items-center rounded-md bg-purple-50 px-2 py-0.5 text-xs font-semibold text-purple-700 border border-purple-200">Admin</span>;
      case "analyst":
        return <span className="inline-flex items-center rounded-md bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700 border border-blue-200">HSE Analyst</span>;
      case "site_manager":
        return <span className="inline-flex items-center rounded-md bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-700 border border-amber-200">Site Manager</span>;
      case "leadership":
        return <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">Leadership</span>;
      default:
        return <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">{r}</span>;
    }
  };

  const getSiteName = (idOrName: string) => {
    const found = sites.find((s) => s.id === idOrName || s.name === idOrName);
    return found ? found.name : idOrName;
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Administration & Governance</h1>
          <p className="mt-1 text-xs text-slate-500">
            Manage user accounts, assign site-scoping permissions, audit system actions, and trigger model calibration.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 border border-indigo-200">
            Active Admin: <strong className="ml-1 font-semibold">{currentUser?.username || "admin"}</strong>
          </span>
        </div>
      </div>

      {/* Main Grid: User Management & Audit Log */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* User Management Section (2 cols) */}
        <section className="lg:col-span-2 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">User Access Management</h2>
              <p className="text-xs text-slate-500">Manage user roles and facility-scoping boundaries</p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search username or email..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 outline-none"
              />
              <select
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
                className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-900 focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 outline-none"
              >
                <option value="all">All Roles</option>
                <option value="admin">Admin</option>
                <option value="analyst">HSE Analyst</option>
                <option value="site_manager">Site Manager</option>
                <option value="leadership">Leadership</option>
              </select>
            </div>
          </div>

          {/* User Table */}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-200 bg-slate-50/70 text-slate-600 font-semibold">
                <tr>
                  <th className="py-2.5 px-3">User</th>
                  <th className="py-2.5 px-3">Role</th>
                  <th className="py-2.5 px-3">Assigned Site Scope</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredUsers.length ? (
                  filteredUsers.map((u) => {
                    const isSelf = currentUser?.user_id === u.id || currentUser?.username === u.username;
                    return (
                      <tr key={u.id} className="hover:bg-slate-50/60 transition">
                        <td className="py-3 px-3">
                          <div className="font-semibold text-slate-900">{u.username}</div>
                          <div className="text-[11px] text-slate-400">{u.email || "No email assigned"}</div>
                        </td>
                        <td className="py-3 px-3">{getRoleBadge(u.role)}</td>
                        <td className="py-3 px-3">
                          {u.role === "leadership" || u.role === "admin" ? (
                            <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                              Org-Wide (All Assets)
                            </span>
                          ) : u.site_scope && u.site_scope.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {u.site_scope.map((sid) => (
                                <span key={sid} className="inline-flex items-center rounded bg-indigo-50 border border-indigo-100 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700">
                                  {getSiteName(sid)}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-[11px] italic text-slate-400">Unscoped</span>
                          )}
                        </td>
                        <td className="py-3 px-3">
                          <button
                            onClick={() => handleToggleActive(u)}
                            disabled={isSelf}
                            title={isSelf ? "Cannot deactivate yourself" : "Click to toggle active status"}
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold border transition ${u.is_active
                                ? "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
                                : "bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100"
                              } ${isSelf ? "opacity-60 cursor-not-allowed" : ""}`}
                          >
                            <span className={`h-1.5 w-1.5 rounded-full mr-1 ${u.is_active ? "bg-emerald-500" : "bg-rose-500"}`}></span>
                            {u.is_active ? "Active" : "Deactivated"}
                          </button>
                        </td>
                        <td className="py-3 px-3 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => openEditModal(u)}
                              className="rounded border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:border-slate-300 hover:bg-slate-50 transition"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleDeleteUser(u)}
                              disabled={isSelf}
                              title={isSelf ? "Cannot delete yourself" : "Delete user"}
                              className={`rounded border border-red-200 bg-red-50/50 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-100 transition ${isSelf ? "opacity-30 cursor-not-allowed" : ""
                                }`}
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-slate-400 italic">
                      No users found matching filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Create User Sub-Form */}
          <div className="mt-6 border-t border-slate-200 pt-5">
            <h3 className="text-sm font-bold text-slate-900">Provision New User Account</h3>
            <p className="text-xs text-slate-500">Add an HSE Analyst, Site Manager, or Leadership account</p>

            <form onSubmit={handleCreateUser} className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <div>
                <label className="block text-xs font-semibold text-slate-700">Username *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. manager_jorhat"
                  value={createUsername}
                  onChange={(e) => setCreateUsername(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-indigo-600 outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Password *</label>
                <input
                  type="password"
                  required
                  placeholder="Minimum 6 characters"
                  value={createPassword}
                  onChange={(e) => setCreatePassword(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-indigo-600 outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">Email Address</label>
                <input
                  type="email"
                  placeholder="user@oilindia.example"
                  value={createEmail}
                  onChange={(e) => setCreateEmail(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-indigo-600 outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">System Role *</label>
                <select
                  value={createRole}
                  onChange={(e) => setCreateRole(e.target.value as Role)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-indigo-600 outline-none"
                >
                  <option value="analyst">HSE Analyst (Triage & Review)</option>
                  <option value="site_manager">Site Manager (Site-Scoped)</option>
                  <option value="leadership">HSSE Leadership (Org-Wide)</option>
                  <option value="admin">System Administrator (Full)</option>
                </select>
              </div>

              {/* Site Scope Checkboxes if Role is Analyst or Site Manager */}
              {(createRole === "analyst" || createRole === "site_manager") && (
                <div className="sm:col-span-2 rounded-lg bg-slate-50 border border-slate-200 p-3">
                  <label className="block text-xs font-semibold text-slate-800 mb-1.5">
                    Assign Operating Asset Scope ({createRole === "site_manager" ? "Select primary site" : "Select assigned sites"})
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {sites.map((s) => {
                      const isChecked = createSiteScope.includes(s.id);
                      return (
                        <label key={s.id} className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setCreateSiteScope([...createSiteScope, s.id]);
                              } else {
                                setCreateSiteScope(createSiteScope.filter((id) => id !== s.id));
                              }
                            }}
                            className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                          />
                          <span>{s.name}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="sm:col-span-2 flex items-center justify-between pt-2">
                <button
                  type="submit"
                  disabled={createLoading}
                  className="rounded-lg bg-indigo-600 hover:bg-indigo-700 px-4 py-2 text-xs font-semibold text-white shadow-sm transition disabled:opacity-50"
                >
                  {createLoading ? "Creating..." : "+ Add User Account"}
                </button>
                {createMessage && (
                  <span className={`text-xs font-medium ${createMessage.type === "success" ? "text-emerald-600" : "text-red-600"}`}>
                    {createMessage.text}
                  </span>
                )}
              </div>
            </form>
          </div>
        </section>

        {/* Audit Trail Section (1 col) */}
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Immutable Audit Trail</h2>
              <p className="text-xs text-slate-500">Append-only administrative log</p>
            </div>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-mono text-slate-600">
              {audit.length} entries
            </span>
          </div>

          <div className="mt-4 max-h-[560px] space-y-2.5 overflow-y-auto pr-1 text-xs">
            {audit.length ? (
              audit.map((row) => (
                <div key={row.id} className="rounded-lg border border-slate-100 bg-slate-50/70 p-3 hover:bg-slate-100/70 transition">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-900 font-mono text-[11px]">{row.action_type}</span>
                    <span className="text-[10px] text-slate-400">
                      {new Date(row.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500">
                    <span>Target: <strong className="font-medium text-slate-700">{row.entity_type}</strong></span>
                    <span>{new Date(row.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-center text-slate-400 italic py-6">No audit records logged yet.</p>
            )}
          </div>
        </section>
      </div>

      {/* Edit User Modal */}
      {editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900">Edit User: {editingUser.username}</h3>
                <p className="text-xs text-slate-500">Update role assignments, site scoping, or reset credentials</p>
              </div>
              <button
                onClick={() => setEditingUser(null)}
                className="text-slate-400 hover:text-slate-600 font-bold text-lg"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveEdit} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="block font-semibold text-slate-700">Role</label>
                <select
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value as Role)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-indigo-600 outline-none"
                >
                  <option value="analyst">HSE Analyst (Triage Queue & Overrides)</option>
                  <option value="site_manager">Site Manager (Site-Scoped Dashboard)</option>
                  <option value="leadership">HSSE Leadership (Org-Wide Read-Only)</option>
                  <option value="admin">System Administrator (Full Access)</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-slate-700">Email Address</label>
                <input
                  type="email"
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-indigo-600 outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700">Reset Password (leave empty to keep existing)</label>
                <input
                  type="password"
                  placeholder="New password..."
                  value={editPassword}
                  onChange={(e) => setEditPassword(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-indigo-600 outline-none"
                />
              </div>

              {/* Site Scoping if Analyst or Site Manager */}
              {(editRole === "analyst" || editRole === "site_manager") && (
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                  <label className="block font-semibold text-slate-800 mb-1.5">Assigned Asset Scopes</label>
                  <div className="grid grid-cols-2 gap-2">
                    {sites.map((s) => {
                      const isChecked = editSiteScope.includes(s.id) || editSiteScope.includes(s.name);
                      return (
                        <label key={s.id} className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setEditSiteScope([...editSiteScope, s.id]);
                              } else {
                                setEditSiteScope(editSiteScope.filter((id) => id !== s.id && id !== s.name));
                              }
                            }}
                            className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                          />
                          <span>{s.name}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="editActiveStatus"
                  checked={editIsActive}
                  onChange={(e) => setEditIsActive(e.target.checked)}
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="editActiveStatus" className="font-semibold text-slate-700 cursor-pointer">
                  Account Active & Allowed to Sign In
                </label>
              </div>

              {editMessage && (
                <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 text-xs text-red-700 font-medium">
                  {editMessage.text}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setEditingUser(null)}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editLoading}
                  className="rounded-lg bg-indigo-600 hover:bg-indigo-700 px-4 py-2 text-xs font-semibold text-white shadow-sm transition disabled:opacity-50"
                >
                  {editLoading ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Active Learning Calibration Section */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Active-Learning Threshold Calibration</h2>
            <p className="mt-1 text-xs text-slate-500">
              Recalibrate the SIF decision threshold from analyst confirmations and overrides. Each run produces an immutable, audit-logged model version.
            </p>
          </div>
          <button
            onClick={onRetrain}
            className="shrink-0 rounded-lg bg-indigo-600 hover:bg-indigo-700 px-4 py-2 text-xs font-semibold text-white shadow-sm transition"
          >
            Run Active Calibration
          </button>
        </div>

        {trainingMessage && (
          <div className="mt-3 rounded-lg bg-indigo-50 border border-indigo-200 p-3 text-xs font-medium text-indigo-800">
            {trainingMessage}
          </div>
        )}

        {trainingRuns.length ? (
          <div className="mt-4 overflow-x-auto">
<<<<<<< HEAD
  <table className="w-full text-left text-xs">
    <thead className="border-b border-slate-200 bg-slate-50/70 text-slate-600 font-semibold">
      <tr>
        <th className="py-2 px-3">Model Version</th>
        <th className="py-2 px-3">Reviewed Reports</th>
        <th className="py-2 px-3">Target Recall</th>
        <th className="py-2 px-3">Calibrated F1</th>
        <th className="py-2 px-3">Created At</th>
      </tr>
    </thead>
    <tbody className="divide-y divide-slate-100">
      {trainingRuns.map((run) => (
        <tr key={run.id} className="hover:bg-slate-50/50">
          <td className="py-2.5 px-3 font-mono font-medium text-slate-900">{run.model_version}</td>
          <td className="py-2.5 px-3">{run.feedback_count}</td>
          <td className="py-2.5 px-3 font-semibold text-emerald-700">{Math.round((run.metrics_after.recall || 0) * 100)}%</td>
          <td className="py-2.5 px-3 font-semibold text-indigo-700">{Math.round((run.metrics_after.f1 || 0) * 100)}%</td>
          <td className="py-2.5 px-3 text-slate-500">{new Date(run.created_at).toLocaleString()}</td>
        </tr>
      ))}
    </tbody>
=======
            <table className="w-full text-left text-[12px]">
      <thead className="text-warm"><tr><th className="py-1 font-medium">Model version</th><th>Reviewed reports</th><th>Recall</th><th>F1</th><th>Created</th></tr></thead>
      <tbody>{trainingRuns.map((run) => <tr key={run.id} className="border-t border-border"><td className="py-2">{run.model_version}</td><td>{run.feedback_count}</td><td>{formatPercent(run.metrics_after.recall || 0)}</td><td>{formatPercent(run.metrics_after.f1 || 0)}</td><td>{new Date(run.created_at).toLocaleString()}</td></tr>)}</tbody>
>>>>>>> 274c737 (Update SIH project features and tests)
    </table>
  </div>
        ) : (
    <p className="mt-4 text-xs text-slate-400 italic">No calibration runs performed yet.</p>
  )
}
      </section >

  {/* Model Evaluation & Performance Section */ }
  < section className = "rounded-xl border border-slate-200 bg-white p-5 shadow-sm" >
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-100 pb-3">
      <div>
        <h2 className="text-lg font-bold text-slate-900">Model Performance & Evaluation Registry</h2>
        <p className="mt-1 text-xs text-slate-500">
          Read-only evaluation artifacts and immutable calibration-run metrics for compliance and audit verification.
        </p>
      </div>
      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-700 border border-slate-200">
        Admin / Leadership Visibility
      </span>
    </div>

{
  evaluationError ? (
    <p className="mt-4 text-xs text-red-600">Unable to load model evaluation: {evaluationError}</p>
  ) : evaluations.length ? (
    <div className="mt-4 space-y-4">
      {evaluations.map((model, index) => {
        const metricLabels: Array<[string, string]> = [
          ["Precision", "precision"],
          ["Recall", "recall"],
          ["F1", "f1"],
          ["Accuracy", "accuracy"],
          ["ROC-AUC", "roc_auc"],
          ["PR-AUC", "pr_auc"],
          ["Specificity", "specificity"],
          ["Brier Score", "brier_score"],
        ];
        const lifecycleClass =
          model.lifecycle === "PRODUCTION"
            ? "bg-emerald-100 text-emerald-800 border-emerald-300"
            : model.lifecycle === "CANDIDATE"
              ? "bg-amber-100 text-amber-800 border-amber-300"
              : model.lifecycle === "RETIRED"
                ? "bg-slate-200 text-slate-700 border-slate-300"
                : "bg-indigo-100 text-indigo-800 border-indigo-300";

        return (
          <article key={`${model.model_name}-${model.model_version || index}`} className="rounded-lg border border-slate-200 bg-slate-50/40 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h3 className="font-bold text-slate-900">{model.model_name}</h3>
                <p className="mt-0.5 font-mono text-[11px] text-slate-500">{model.model_version || "Version not stored in artifact"}</p>
              </div>
              <span className={`rounded px-2 py-0.5 text-[10px] font-bold border ${lifecycleClass}`}>
                {model.lifecycle}
              </span>
            </div>

            {model.data_provenance?.startsWith("DEMO_FALLBACK") && (
              <p className="mt-3 rounded border border-amber-300 bg-amber-50 p-2 text-xs font-semibold text-amber-900">
                Demo/synthetic fallback: these performance metrics are not human-validated OIL results.
              </p>
            )}

            <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
              {[
                ["Training date", model.training_date ? new Date(model.training_date).toLocaleString() : "—"],
                ["Dataset", model.dataset_version || "—"],
                ["Data provenance", model.data_provenance || "UNKNOWN"],
                ["Training", model.training_samples ?? "—"],
                ["Validation", model.validation_samples ?? "—"],
                ["Test", model.test_samples ?? "—"],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded border border-slate-200 bg-white p-2">
                  <div className="text-[10px] text-slate-500">{label}</div>
                  <div className="mt-0.5 break-words font-medium text-slate-800">{value}</div>
                </div>
              ))}
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
              {metricLabels.map(([label, key]) => (
                <div key={key} className="rounded border border-slate-200 bg-white p-2 text-xs">
                  <div className="text-[10px] text-slate-500">{label}</div>
                  <div className="mt-0.5 font-mono font-bold text-slate-900">
                    {model.metrics[key] === null || model.metrics[key] === undefined ? "—" : Number(model.metrics[key]).toFixed(3)}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div className="rounded border border-slate-200 bg-white p-3">
                <div className="text-xs font-bold text-slate-800">Confusion Matrix</div>
                <div className="mt-2 grid grid-cols-2 gap-1.5 text-center text-xs">
                  <span className="rounded bg-slate-100 p-2 font-medium">TN {model.confusion_matrix.tn ?? "—"}</span>
                  <span className="rounded bg-amber-50 text-amber-800 p-2 font-medium">FP {model.confusion_matrix.fp ?? "—"}</span>
                  <span className="rounded bg-rose-50 text-rose-800 p-2 font-medium">FN {model.confusion_matrix.fn ?? "—"}</span>
                  <span className="rounded bg-emerald-50 text-emerald-800 p-2 font-medium">TP {model.confusion_matrix.tp ?? "—"}</span>
                </div>
              </div>
              <div className="rounded border border-slate-200 bg-white p-3">
                <div className="text-xs font-bold text-slate-800">Calibration Diagnostics</div>
                <div className="mt-2 grid grid-cols-2 gap-1.5 text-xs">
                  {Object.keys(model.calibration).length ? (
                    Object.entries(model.calibration).map(([key, value]) => (
                      <div key={key} className="rounded bg-slate-50 p-2">
                        <span className="text-slate-500">{key.replaceAll("_", " ")}: </span>
                        <strong className="text-slate-900">{value === null ? "—" : Number(value).toFixed(3)}</strong>
                      </div>
                    ))
                  ) : (
                    <span className="text-slate-400 italic">No calibration diagnostics stored.</span>
                  )}
                </div>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  ) : (
    <p className="mt-4 text-xs text-slate-400 italic">No stored evaluation artifacts are available.</p>
  )
}
      </section >
    </div >
  );
}
