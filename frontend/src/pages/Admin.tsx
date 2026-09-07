import { FormEvent, useEffect, useState } from "react";
import { api, type Role } from "../api";

export function AdminPage() {
  const [users, setUsers] = useState<Array<{ id: string; username: string; role: Role; is_active: boolean; email?: string }>>([]);
  const [audit, setAudit] = useState<Array<{ id: string; action_type: string; entity_type: string; created_at: string; user_id: string | null }>>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("analyst");
  const [message, setMessage] = useState("");
  const [trainingMessage, setTrainingMessage] = useState("");
  const [trainingRuns, setTrainingRuns] = useState<Array<{ id: string; model_version: string; feedback_count: number; metrics_before: Record<string, number>; metrics_after: Record<string, number>; created_at: string }>>([]);

  function load() {
    api.users().then(setUsers);
    api.audit().then(setAudit);
    api.trainingRuns().then(setTrainingRuns);
  }

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

  useEffect(() => {
    load();
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setMessage("");
    await api.createUser({ username, password, role });
    setUsername("");
    setPassword("");
    setMessage("User created.");
    load();
  }

  return (
    <div>
      <h1 className="text-[24px] font-semibold">Admin</h1>
      <p className="mt-1 text-warm">Users, roles, and an append-only audit trail. Historical classifications cannot be deleted here.</p>

      <div className="mt-6 grid grid-cols-2 gap-4">
        <section className="rounded-[10px] border border-border bg-white p-5 shadow-card">
          <h2 className="text-[18px] font-semibold">Users</h2>
          <table className="mt-3 w-full text-left text-[13px]">
            <thead className="text-warm">
              <tr>
                <th className="py-1 font-medium">Username</th>
                <th>Role</th>
                <th>Active</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-border">
                  <td className="py-2">{u.username}</td>
                  <td className="capitalize">{u.role.replace("_", " ")}</td>
                  <td>{u.is_active ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <form onSubmit={onCreate} className="mt-6 space-y-3 border-t border-border pt-4">
            <div className="text-[13px] font-medium">Add user</div>
            <input
              className="w-full rounded-[6px] border border-muted px-3 py-2"
              placeholder="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
            <input
              className="w-full rounded-[6px] border border-muted px-3 py-2"
              placeholder="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <select className="w-full rounded-[6px] border border-muted px-3 py-2" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              <option value="analyst">analyst</option>
              <option value="site_manager">site_manager</option>
              <option value="leadership">leadership</option>
              <option value="admin">admin</option>
            </select>
            <button className="rounded-[8px] bg-cyan px-4 py-2 font-medium text-white">Save user</button>
            {message ? <p className="text-risk-low">{message}</p> : null}
          </form>
        </section>

        <section className="rounded-[10px] border border-border bg-white p-5 shadow-card">
          <h2 className="text-[18px] font-semibold">Audit log</h2>
          <div className="mt-3 max-h-[640px] overflow-auto">
            {audit.map((row) => (
              <div key={row.id} className="border-b border-border py-2 text-[12px]">
                <div className="font-medium">{row.action_type}</div>
                <div className="text-warm">
                  {row.entity_type} · {new Date(row.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="mt-4 rounded-[10px] border border-border bg-white p-5 shadow-card">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[18px] font-semibold">Active-learning calibration</h2>
            <p className="mt-1 text-[13px] text-warm">Recalibrate the SIF decision threshold from analyst confirmations and overrides. Each run is audit logged.</p>
          </div>
          <button onClick={onRetrain} className="shrink-0 rounded-[8px] bg-cyan px-4 py-2 text-[13px] font-medium text-white">Run calibration</button>
        </div>
        {trainingMessage ? <p className="mt-3 text-[13px] text-warm">{trainingMessage}</p> : null}
        {trainingRuns.length ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-[12px]">
              <thead className="text-warm"><tr><th className="py-1 font-medium">Model version</th><th>Reviewed reports</th><th>Recall</th><th>F1</th><th>Created</th></tr></thead>
              <tbody>{trainingRuns.map((run) => <tr key={run.id} className="border-t border-border"><td className="py-2">{run.model_version}</td><td>{run.feedback_count}</td><td>{Math.round((run.metrics_after.recall || 0) * 100)}%</td><td>{Math.round((run.metrics_after.f1 || 0) * 100)}%</td><td>{new Date(run.created_at).toLocaleString()}</td></tr>)}</tbody>
            </table>
          </div>
        ) : <p className="mt-4 text-[13px] text-warm">No calibration runs yet.</p>}
      </section>
    </div>
  );
}
