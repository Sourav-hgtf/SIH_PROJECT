import { FormEvent, useEffect, useState } from "react";
import { api, type ModelEvaluationRecord, type Role } from "../api";

export function AdminPage() {
  const [users, setUsers] = useState<Array<{ id: string; username: string; role: Role; is_active: boolean; email?: string }>>([]);
  const [audit, setAudit] = useState<Array<{ id: string; action_type: string; entity_type: string; created_at: string; user_id: string | null }>>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("analyst");
  const [message, setMessage] = useState("");
  const [trainingMessage, setTrainingMessage] = useState("");
  const [trainingRuns, setTrainingRuns] = useState<Array<{ id: string; model_version: string; feedback_count: number; metrics_before: Record<string, number>; metrics_after: Record<string, number>; created_at: string }>>([]);
  const [evaluations, setEvaluations] = useState<ModelEvaluationRecord[]>([]);
  const [evaluationError, setEvaluationError] = useState("");

  function load() {
    api.users().then(setUsers);
    api.audit().then(setAudit);
    api.trainingRuns().then(setTrainingRuns);
    api.modelEvaluation().then((data) => setEvaluations(data.records)).catch((error) => setEvaluationError(error.message));
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

      <section className="mt-4 rounded-[10px] border border-border bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border pb-3">
          <div>
            <h2 className="text-[18px] font-semibold">Model performance & audit</h2>
            <p className="mt-1 text-[13px] text-warm">Read-only evaluation artifacts and immutable calibration-run metrics. Blank fields mean the stored source did not provide that value.</p>
          </div>
          <span className="rounded bg-slate-100 px-2 py-1 text-[11px] font-medium text-warm">Admin / leadership visibility</span>
        </div>
        {evaluationError ? <p className="mt-4 text-[13px] text-risk-critical">Unable to load model evaluation: {evaluationError}</p> : evaluations.length ? (
          <div className="mt-4 space-y-4">
            {evaluations.map((model, index) => {
              const metricLabels: Array<[string, string]> = [["Precision", "precision"], ["Recall", "recall"], ["F1", "f1"], ["Accuracy", "accuracy"], ["ROC-AUC", "roc_auc"], ["PR-AUC", "pr_auc"], ["Specificity", "specificity"], ["Brier Score", "brier_score"]];
              const lifecycleClass = model.lifecycle === "PRODUCTION" ? "bg-emerald-100 text-emerald-800" : model.lifecycle === "CANDIDATE" ? "bg-amber-100 text-amber-800" : model.lifecycle === "RETIRED" ? "bg-slate-200 text-slate-700" : "bg-indigo-100 text-indigo-800";
              return <article key={`${model.model_name}-${model.model_version || index}`} className="rounded-lg border border-border bg-slate-50/40 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-semibold text-ink">{model.model_name}</h3><p className="mt-0.5 font-mono text-[11px] text-warm">{model.model_version || "Version not stored in artifact"}</p></div><span className={`rounded px-2 py-1 text-[10px] font-bold ${lifecycleClass}`}>{model.lifecycle}</span></div>
                {model.data_provenance?.startsWith("DEMO_FALLBACK") ? <p className="mt-3 rounded border border-amber-300 bg-amber-50 p-2 text-[12px] font-semibold text-amber-900">Demo/synthetic fallback: these performance metrics are not human-validated OIL results.</p> : null}
                <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-3 lg:grid-cols-6">
                  {[["Training date", model.training_date ? new Date(model.training_date).toLocaleString() : "—"], ["Dataset", model.dataset_version || "—"], ["Data provenance", model.data_provenance || "UNKNOWN"], ["Training", model.training_samples ?? "—"], ["Validation", model.validation_samples ?? "—"], ["Test", model.test_samples ?? "—"], ["False positives", model.false_positives ?? "—"], ["False negatives", model.false_negatives ?? "—"]].map(([label, value]) => <div key={String(label)} className="rounded border border-border bg-white p-2"><div className="text-[10px] text-warm">{label}</div><div className="mt-0.5 break-words font-medium text-ink">{value}</div></div>)}
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">{metricLabels.map(([label, key]) => <div key={key} className="rounded border border-border bg-white p-2 text-[11px]"><div className="text-warm">{label}</div><div className="mt-0.5 font-mono font-semibold text-ink">{model.metrics[key] === null || model.metrics[key] === undefined ? "—" : Number(model.metrics[key]).toFixed(3)}</div></div>)}</div>
                <div className="mt-3 grid gap-3 md:grid-cols-2"><div className="rounded border border-border bg-white p-3"><div className="text-xs font-semibold text-ink">Confusion matrix</div><div className="mt-2 grid grid-cols-2 gap-1 text-center text-[11px]"><span className="rounded bg-slate-100 p-2">TN {model.confusion_matrix.tn ?? "—"}</span><span className="rounded bg-amber-50 p-2">FP {model.confusion_matrix.fp ?? "—"}</span><span className="rounded bg-rose-50 p-2">FN {model.confusion_matrix.fn ?? "—"}</span><span className="rounded bg-emerald-50 p-2">TP {model.confusion_matrix.tp ?? "—"}</span></div></div><div className="rounded border border-border bg-white p-3"><div className="text-xs font-semibold text-ink">Calibration</div><div className="mt-2 grid grid-cols-2 gap-1 text-[11px]">{Object.keys(model.calibration).length ? Object.entries(model.calibration).map(([key, value]) => <div key={key} className="rounded bg-slate-50 p-2"><span className="text-warm">{key.replaceAll("_", " ")}: </span><strong>{value === null ? "—" : Number(value).toFixed(3)}</strong></div>) : <span className="text-warm">No calibration diagnostics stored.</span>}</div></div></div>
              </article>;
            })}
          </div>
        ) : <p className="mt-4 text-[13px] text-warm">No stored evaluation artifacts are available.</p>}
      </section>
    </div>
  );
}
