import { useEffect, useState, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  api,
  type IngestionJobOut,
  type IngestionQualityReport,
  type ReportUploadItem,
  type ValidatedRowPreview,
} from "../api";

const SAMPLE_CSV_DATA = `source_report_id,reported_at,site_name,department,shift,equipment_type,job_type,report_type,raw_text
INC-2026-081,2026-03-05T09:15:00Z,Alpha Platform,Drilling,Day,BOP Accumulator,Well Operations,near_miss,"High pressure hydraulic line burst on BOP accumulator during pressure test. Standby technician John Doe (EMP-4821) was standing 2 meters away in the direct line of fire. Emergency ESD switch activated immediately."
INC-2026-082,2026-03-05T13:40:00Z,Beta Refinery,Maintenance,Day,Scaffolding,Working at Height,ua_uc,"Scaffold rigger disconnected dual lanyards while moving between platform levels at 12m height. No fall arrest netting installed underneath."
INC-2026-083,2026-03-05T16:20:00Z,Gamma Terminal,Logistics,Night,Forklift 04,Material Handling,near_miss,"Forklift operator carrying heavy drill pipe bundle reversed across main pedestrian crossing without sounding horn or using spotter."
INC-2026-084,2026-03-06T02:10:00Z,Alpha Platform,Electrical,Night,Switchgear MCC-2,Energy Isolation,near_miss,"Electrician opened 4160V motor control breaker without checking voltage presence or applying physical padlock lock-out tag-out device."
INC-2026-085,2026-03-06T11:00:00Z,Beta Refinery,Operations,Day,Storage Tank T-104,Confined Space,near_miss,"Entry watchman left post at vessel manway while two contractors were inside performing sludge removal without continuous multi-gas monitor."
INC-2026-086,2026-03-06T15:45:00Z,Gamma Terminal,Maintenance,Day,Diesel Generator,Hot Work,near_miss,"Welder struck arc 3 meters from open hydrocarbon drain without hot work permit or continuous LEL combustible gas test."
INC-2026-087,2026-03-07T08:00:00Z,Alpha Platform,Deck Operations,Day,Pedestal Crane 1,Lifting Operations,incident,"Rigging sling snapped during 4-ton container transfer to supply vessel due to worn wire rope strands and dynamic swell impact."
INC-2026-088,2026-03-07T10:30:00Z,Beta Refinery,Drilling,Day,Mud Pump 2,Maintenance,ua_uc,"Pump technician adjusted pulsation dampener valve while mud pump was energized at 2800 PSI."`;

export function IngestionPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<"upload" | "preview" | "processing" | "complete">("upload");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Quality Report & rows to ingest
  const [qualityReport, setQualityReport] = useState<IngestionQualityReport | null>(null);
  const [currentFile, setCurrentFile] = useState<File | null>(null);
  const [sourceName, setSourceName] = useState<string>("Manual Ingestion");
  const [validatedRows, setValidatedRows] = useState<ReportUploadItem[]>([]);
  const [sites, setSites] = useState<Array<{ id: string; name: string; region: string }>>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");

  // Job progress tracking
  const [activeJob, setActiveJob] = useState<IngestionJobOut | null>(null);
  const [recentJobs, setRecentJobs] = useState<IngestionJobOut[]>([]);

  // Manual entry modal / tab state
  const [activeTab, setActiveTab] = useState<"file" | "manual" | "sample">("file");
  const [manualText, setManualText] = useState("");
  const [manualSite, setManualSite] = useState("");
  const [manualDept, setManualDept] = useState("Drilling");
  const [manualType, setManualType] = useState("near_miss");

  useEffect(() => {
    loadSitesAndJobs();
  }, []);

  async function loadSitesAndJobs() {
    try {
      const [sList, jList] = await Promise.all([api.sites(), api.ingestionJobs()]);
      setSites(sList);
      if (sList.length > 0) setSelectedSiteId(sList[0].id);
      setRecentJobs(jList);
    } catch (e) {
      console.error("Failed loading sites or jobs", e);
    }
  }

  // Poll job status during processing
  useEffect(() => {
    if (step !== "processing" || !activeJob || activeJob.status === "COMPLETED" || activeJob.status === "FAILED") {
      return;
    }
    const timer = setInterval(async () => {
      try {
        const updated = await api.ingestionJobStatus(activeJob.id);
        setActiveJob(updated);
        if (updated.status === "COMPLETED") {
          setStep("complete");
          loadSitesAndJobs();
        } else if (updated.status === "FAILED") {
          setError("Ingestion job failed. See error details below.");
          loadSitesAndJobs();
        }
      } catch (e) {
        console.error("Error polling job", e);
      }
    }, 1200);
    return () => clearInterval(timer);
  }, [step, activeJob]);

  // Handle File Upload
  async function handleFileUpload(file: File) {
    setLoading(true);
    setError(null);
    setCurrentFile(file);
    setSourceName(file.name);
    try {
      const report = await api.validateIngestionFile(file);
      setQualityReport(report);
      // Construct validated rows for confirmation
      const rowsToSubmit: ReportUploadItem[] = report.preview_rows
        .filter((r) => r.is_valid)
        .map((r) => ({
          source_report_id: (r.data.source_report_id as string) || null,
          report_type: (r.data.report_type as string) || "near_miss",
          site_id: (r.data.site_id as string) || null,
          site_name: (r.data.site_name as string) || null,
          department: (r.data.department as string) || null,
          shift: (r.data.shift as string) || null,
          equipment_type: (r.data.equipment_type as string) || null,
          job_type: (r.data.job_type as string) || null,
          raw_text: (r.data.raw_text as string) || "",
          reported_at: (r.data.reported_at as string) || null,
        }));
      setValidatedRows(rowsToSubmit);
      setStep("preview");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "File validation failed.");
    } finally {
      setLoading(false);
    }
  }

  // Handle Sample Dataset Load
  async function handleLoadSample() {
    const blob = new Blob([SAMPLE_CSV_DATA], { type: "text/csv" });
    const file = new File([blob], "oil_india_sample_hse_batch.csv", { type: "text/csv" });
    await handleFileUpload(file);
  }

  // Handle Manual Entry Submit
  async function handleManualSubmit() {
    if (!manualText.trim() || manualText.trim().length < 10) {
      setError("Please enter a detailed incident description (at least 10 characters).");
      return;
    }
    setLoading(true);
    setError(null);
    setSourceName("Direct Single Entry");

    const singleRow: ReportUploadItem = {
      source_report_id: `MANUAL-${Date.now().toString().slice(-6)}`,
      report_type: manualType,
      site_id: manualSite || (sites[0]?.id ?? null),
      department: manualDept,
      raw_text: manualText,
      reported_at: new Date().toISOString(),
    };

    try {
      const report = await api.validateIngestionJson([singleRow]);
      setQualityReport(report);
      setValidatedRows([singleRow]);
      setStep("preview");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Validation failed.");
    } finally {
      setLoading(false);
    }
  }

  // Handle Confirm Ingestion
  async function handleConfirm() {
    if (validatedRows.length === 0) {
      setError("No valid rows to ingest.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const job = await api.confirmIngestion({
        rows: validatedRows,
        source_name: sourceName,
        default_site_id: selectedSiteId || undefined,
      });
      setActiveJob(job);
      setStep("processing");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to trigger ingestion.");
    } finally {
      setLoading(false);
    }
  }

  function renderQualityScoreBadge(score: number) {
    let color = "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
    let label = "High Quality";
    if (score < 60) {
      color = "bg-rose-500/20 text-rose-300 border-rose-500/40";
      label = "Needs Review";
    } else if (score < 85) {
      color = "bg-amber-500/20 text-amber-300 border-amber-500/40";
      label = "Acceptable Quality";
    }

    return (
      <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-semibold ${color}`}>
        <span>Score: {score}%</span>
        <span className="opacity-70">•</span>
        <span>{label}</span>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-6xl mx-auto pb-12">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-3">
            <span>HSE Report Ingestion & Data Quality Pipeline</span>
            <span className="text-xs px-2.5 py-0.5 rounded bg-cyan/20 text-cyan border border-cyan/30">Production Ingest</span>
          </h1>
          <p className="mt-1 text-sm text-ash">
            Upload CSV/JSON safety datasets, execute automated data quality audits, redact PII, and run full AI pipeline analysis.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="/v1/ingestion/template"
            download
            className="inline-flex items-center gap-2 rounded bg-white/10 hover:bg-white/15 px-3 py-2 text-xs font-medium text-white transition border border-white/15"
          >
            <svg className="w-4 h-4 text-cyan" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download CSV Template
          </a>
        </div>
      </div>

      {/* Workflow Step Indicators */}
      <div className="grid grid-cols-4 gap-3 text-xs font-medium">
        <div className={`p-3 rounded border transition ${step === "upload" ? "bg-cyan/10 border-cyan text-cyan" : "bg-card border-white/5 text-ash"}`}>
          <div className="font-semibold">Step 1</div>
          <div>Upload or Input Dataset</div>
        </div>
        <div className={`p-3 rounded border transition ${step === "preview" ? "bg-cyan/10 border-cyan text-cyan" : "bg-card border-white/5 text-ash"}`}>
          <div className="font-semibold">Step 2</div>
          <div>Data Quality & PII Audit</div>
        </div>
        <div className={`p-3 rounded border transition ${step === "processing" ? "bg-cyan/10 border-cyan text-cyan animate-pulse" : "bg-card border-white/5 text-ash"}`}>
          <div className="font-semibold">Step 3</div>
          <div>AI SIF & LSR Extraction</div>
        </div>
        <div className={`p-3 rounded border transition ${step === "complete" ? "bg-emerald-500/10 border-emerald-500 text-emerald-400" : "bg-card border-white/5 text-ash"}`}>
          <div className="font-semibold">Step 4</div>
          <div>Ingested & Available</div>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded bg-rose-950/40 border border-rose-500/40 text-rose-200 text-sm flex items-start gap-3">
          <span className="h-2 w-2 rounded-full bg-rose-400 mt-1.5 shrink-0" />
          <div className="flex-1">{error}</div>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-white text-xs">Dismiss</button>
        </div>
      )}

      {/* STEP 1: UPLOAD / INPUT */}
      {step === "upload" && (
        <div className="space-y-6">
          <div className="flex border-b border-white/10 gap-4 text-sm font-medium">
            <button
              onClick={() => setActiveTab("file")}
              className={`pb-3 border-b-2 transition ${activeTab === "file" ? "border-cyan text-cyan" : "border-transparent text-ash hover:text-white"}`}
            >
              File Upload (CSV / JSON)
            </button>
            <button
              onClick={() => setActiveTab("sample")}
              className={`pb-3 border-b-2 transition ${activeTab === "sample" ? "border-cyan text-cyan" : "border-transparent text-ash hover:text-white"}`}
            >
              Demo Sample Dataset (1-Click)
            </button>
            <button
              onClick={() => setActiveTab("manual")}
              className={`pb-3 border-b-2 transition ${activeTab === "manual" ? "border-cyan text-cyan" : "border-transparent text-ash hover:text-white"}`}
            >
              Direct Incident Form
            </button>
          </div>

          {activeTab === "file" && (
            <div className="bg-card border border-white/10 rounded-lg p-8">
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.json"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFileUpload(file);
                }}
              />
              <div
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const file = e.dataTransfer.files?.[0];
                  if (file) handleFileUpload(file);
                }}
                className="border-2 border-dashed border-white/20 hover:border-cyan/60 rounded-xl p-12 text-center cursor-pointer transition bg-white/[0.02] hover:bg-cyan/[0.02]"
              >
                <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-cyan/10 border border-cyan/30 flex items-center justify-center text-cyan">
                  <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                <h3 className="text-base font-semibold text-white">Drag & drop your HSE dataset here</h3>
                <p className="text-xs text-ash mt-1">Supports standard CSV and JSON incident report exports</p>
                <button
                  type="button"
                  disabled={loading}
                  className="mt-5 inline-flex items-center gap-2 rounded bg-cyan hover:bg-cyan/90 text-soot px-4 py-2 text-xs font-semibold shadow transition"
                >
                  {loading ? "Analyzing File..." : "Browse Local File"}
                </button>
              </div>

              <div className="mt-6 grid grid-cols-3 gap-4 text-xs text-ash border-t border-white/10 pt-4">
                <div className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan mt-1.5 shrink-0" />
                  <span>Automated column header mapping (ID, Date, Narrative, Equipment, Shift)</span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan mt-1.5 shrink-0" />
                  <span>Automatic PII Redaction for personnel names, IDs, phone numbers, and emails</span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan mt-1.5 shrink-0" />
                  <span>Instant duplicate checking against historical incident database</span>
                </div>
              </div>
            </div>
          )}

          {activeTab === "sample" && (
            <div className="bg-card border border-white/10 rounded-lg p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">Judge Demo Sample Dataset</h3>
                  <p className="text-xs text-ash">Pre-loaded multi-site oilfield batch containing 8 realistic incidents with varying SIF precursors, LSR violations, and energy hazards.</p>
                </div>
                <button
                  onClick={handleLoadSample}
                  disabled={loading}
                  className="rounded bg-cyan hover:bg-cyan/90 text-soot px-4 py-2 text-xs font-semibold shadow transition"
                >
                  {loading ? "Analyzing..." : "Load & Inspect Demo Batch"}
                </button>
              </div>
              <div className="p-3 bg-soot/60 rounded border border-white/5 font-mono text-[11px] text-ash/80 overflow-x-auto max-h-48">
                <pre>{SAMPLE_CSV_DATA}</pre>
              </div>
            </div>
          )}

          {activeTab === "manual" && (
            <div className="bg-card border border-white/10 rounded-lg p-6 space-y-4">
              <h3 className="text-sm font-semibold text-white">Direct Incident Entry</h3>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-medium text-ash mb-1">Site / Facility</label>
                  <select
                    value={manualSite}
                    onChange={(e) => setManualSite(e.target.value)}
                    className="w-full rounded bg-soot border border-white/15 px-3 py-2 text-xs text-white"
                  >
                    {sites.map((s) => (
                      <option key={s.id} value={s.id}>{s.name} ({s.region})</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-ash mb-1">Department</label>
                  <input
                    type="text"
                    value={manualDept}
                    onChange={(e) => setManualDept(e.target.value)}
                    className="w-full rounded bg-soot border border-white/15 px-3 py-2 text-xs text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-ash mb-1">Report Type</label>
                  <select
                    value={manualType}
                    onChange={(e) => setManualType(e.target.value)}
                    className="w-full rounded bg-soot border border-white/15 px-3 py-2 text-xs text-white"
                  >
                    <option value="near_miss">Near Miss</option>
                    <option value="incident">Incident / Loss</option>
                    <option value="ua_uc">Unsafe Act / Condition (UA/UC)</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-ash mb-1">Incident Narrative (Raw Text)</label>
                <textarea
                  rows={4}
                  value={manualText}
                  onChange={(e) => setManualText(e.target.value)}
                  placeholder="Describe the safety observation, precursor event, energy hazard, equipment involved, and actions taken..."
                  className="w-full rounded bg-soot border border-white/15 p-3 text-xs text-white focus:outline-none focus:border-cyan"
                />
              </div>
              <div className="flex justify-end">
                <button
                  onClick={handleManualSubmit}
                  disabled={loading}
                  className="rounded bg-cyan hover:bg-cyan/90 text-soot px-4 py-2 text-xs font-semibold shadow transition"
                >
                  {loading ? "Validating..." : "Validate & Audit Entry"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* STEP 2: PREVIEW & DATA QUALITY AUDIT */}
      {step === "preview" && qualityReport && (
        <div className="space-y-6">
          {/* Header Bar */}
          <div className="flex flex-wrap items-center justify-between gap-4 bg-card border border-white/10 rounded-lg p-5">
            <div>
              <div className="text-xs text-ash">Analyzed Source: <span className="text-white font-medium">{sourceName}</span></div>
              <div className="text-lg font-bold text-white mt-0.5 flex items-center gap-3">
                <span>Data Quality & Integrity Audit</span>
                {renderQualityScoreBadge(qualityReport.data_quality_score)}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setStep("upload")}
                className="rounded bg-white/10 hover:bg-white/15 px-4 py-2 text-xs font-medium text-white transition"
              >
                Back / Choose Another
              </button>
              <button
                onClick={handleConfirm}
                disabled={loading || qualityReport.valid_rows === 0}
                className="rounded bg-cyan hover:bg-cyan/90 text-soot px-5 py-2 text-xs font-bold shadow transition flex items-center gap-2"
              >
                {loading ? "Enqueuing Pipeline..." : `Confirm & Ingest ${qualityReport.valid_rows} Valid Reports`}
              </button>
            </div>
          </div>

          {/* Metric Cards */}
          <div className="grid grid-cols-5 gap-4">
            <div className="bg-card border border-white/10 rounded-lg p-4">
              <div className="text-xs text-ash">Total Records</div>
              <div className="text-2xl font-bold text-white mt-1">{qualityReport.total_rows}</div>
            </div>
            <div className="bg-card border border-white/10 rounded-lg p-4">
              <div className="text-xs text-emerald-400">Valid Records</div>
              <div className="text-2xl font-bold text-emerald-400 mt-1">{qualityReport.valid_rows}</div>
            </div>
            <div className="bg-card border border-white/10 rounded-lg p-4">
              <div className="text-xs text-rose-400">Invalid Records</div>
              <div className="text-2xl font-bold text-rose-400 mt-1">{qualityReport.invalid_rows}</div>
            </div>
            <div className="bg-card border border-white/10 rounded-lg p-4">
              <div className="text-xs text-amber-400">Duplicates Detected</div>
              <div className="text-2xl font-bold text-amber-400 mt-1">{qualityReport.duplicate_rows}</div>
            </div>
            <div className="bg-card border border-white/10 rounded-lg p-4">
              <div className="text-xs text-cyan">PII Redactions</div>
              <div className="text-2xl font-bold text-cyan mt-1">{qualityReport.pii_total_redactions}</div>
            </div>
          </div>

          {/* Completeness & Issues */}
          <div className="grid grid-cols-3 gap-6">
            <div className="bg-card border border-white/10 rounded-lg p-5 col-span-1 space-y-3">
              <h4 className="text-xs font-semibold text-white uppercase tracking-wider">Field Completeness</h4>
              <div className="space-y-2.5">
                {Object.entries(qualityReport.completeness_breakdown).map(([field, pct]) => (
                  <div key={field} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-ash capitalize">{field.replace("_", " ")}</span>
                      <span className="text-white font-medium">{pct}%</span>
                    </div>
                    <div className="w-full bg-soot rounded-full h-1.5 overflow-hidden">
                      <div className="bg-cyan h-1.5 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-card border border-white/10 rounded-lg p-5 col-span-2 space-y-3">
              <h4 className="text-xs font-semibold text-white uppercase tracking-wider">Audit Findings & Actions</h4>
              <div className="space-y-2">
                {qualityReport.pii_total_redactions > 0 && (
                  <div className="p-3 bg-cyan/10 border border-cyan/30 rounded text-xs text-cyan flex items-center justify-between">
                    <span>Automated PII Guard: {qualityReport.pii_total_redactions} sensitive entity tokens (Names, Badges, Phone Numbers) will be scrubbed before database commit.</span>
                    <span className="font-semibold uppercase tracking-wider text-[10px] bg-cyan/20 px-2 py-0.5 rounded">Active</span>
                  </div>
                )}
                {qualityReport.duplicate_rows > 0 && (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-300">
                    {qualityReport.duplicate_rows} duplicate report ID(s) detected. Reports with existing IDs will be processed under unique identifiers to prevent overwrites.
                  </div>
                )}
                {qualityReport.invalid_rows > 0 && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded text-xs text-rose-300">
                    {qualityReport.invalid_rows} row(s) lack sufficient narrative text (&lt; 10 chars) and will be excluded during ingestion.
                  </div>
                )}
                {qualityReport.invalid_rows === 0 && qualityReport.duplicate_rows === 0 && (
                  <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs text-emerald-300">
                    All records passed schema validation checks cleanly.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Preview Table */}
          <div className="bg-card border border-white/10 rounded-lg overflow-hidden">
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <h4 className="text-sm font-semibold text-white">Record Preview ({qualityReport.preview_rows.length} rows displayed)</h4>
              <span className="text-xs text-ash">Showing mapped fields and PII redaction previews</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-white/5 text-ash uppercase font-semibold border-b border-white/10">
                  <tr>
                    <th className="p-3">#</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Report ID</th>
                    <th className="p-3">Site / Dept</th>
                    <th className="p-3">Redacted Incident Preview</th>
                    <th className="p-3">PII</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {qualityReport.preview_rows.map((row) => (
                    <tr key={row.row_index} className="hover:bg-white/[0.02]">
                      <td className="p-3 font-mono text-ash">{row.row_index}</td>
                      <td className="p-3">
                        {row.is_valid ? (
                          <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] font-semibold">
                            VALID
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30 text-[10px] font-semibold">
                            INVALID
                          </span>
                        )}
                        {row.is_duplicate && (
                          <span className="ml-1 px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30 text-[10px] font-semibold">
                            DUP
                          </span>
                        )}
                      </td>
                      <td className="p-3 font-mono text-white">{(row.data.source_report_id as string) || "Auto-gen"}</td>
                      <td className="p-3 text-ash">
                        <div className="text-white font-medium">{(row.data.site_name as string) || "Alpha Platform"}</div>
                        <div className="text-[10px]">{(row.data.department as string) || "Operations"}</div>
                      </td>
                      <td className="p-3 text-white max-w-md">
                        <div>{row.pii_redacted_text}</div>
                        {row.issues.length > 0 && (
                          <div className="mt-1 space-y-0.5">
                            {row.issues.map((iss, i) => (
                              <div key={i} className={`text-[10px] ${iss.severity === "error" ? "text-rose-400" : iss.severity === "warning" ? "text-amber-400" : "text-cyan"}`}>
                                • {iss.message}
                              </div>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="p-3">
                        {row.pii_count > 0 ? (
                          <span className="px-1.5 py-0.5 rounded bg-cyan/20 text-cyan text-[10px] font-mono">
                            {row.pii_count} redacted
                          </span>
                        ) : (
                          <span className="text-ash text-[10px]">None</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* STEP 3: PROCESSING WITH LIVE PROGRESS */}
      {step === "processing" && activeJob && (
        <div className="bg-card border border-white/10 rounded-lg p-10 text-center max-w-xl mx-auto space-y-6">
          <div className="w-16 h-16 mx-auto rounded-full bg-cyan/10 border border-cyan/40 flex items-center justify-center text-cyan animate-spin">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">AI Safety Intelligence Pipeline Active</h3>
            <p className="text-xs text-ash mt-1">Processing records through SIF classifier, Life-Saving Rules tagger, semantic precursor clustering, and action recommender.</p>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-ash">Processed {activeJob.processed_count} of {activeJob.record_count} reports</span>
              <span className="text-cyan font-bold">
                {activeJob.record_count > 0 ? Math.round((activeJob.processed_count / activeJob.record_count) * 100) : 0}%
              </span>
            </div>
            <div className="w-full bg-soot rounded-full h-3 overflow-hidden border border-white/10">
              <div
                className="bg-cyan h-3 rounded-full transition-all duration-300"
                style={{
                  width: `${activeJob.record_count > 0 ? (activeJob.processed_count / activeJob.record_count) * 100 : 0}%`,
                }}
              />
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2 text-[11px] text-ash border-t border-white/10 pt-4">
            <div className="text-cyan">1. SIF Probability</div>
            <div className="text-cyan">2. LSR Tagging</div>
            <div className="text-cyan">3. Triples & Clusters</div>
            <div className="text-cyan">4. Actions</div>
          </div>
        </div>
      )}

      {/* STEP 4: COMPLETE */}
      {step === "complete" && activeJob && (
        <div className="bg-card border border-white/10 rounded-lg p-10 text-center max-w-xl mx-auto space-y-6">
          <div className="w-16 h-16 mx-auto rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div>
            <h3 className="text-xl font-bold text-white">Ingestion & AI Analysis Completed</h3>
            <p className="text-xs text-ash mt-1">
              Successfully processed <span className="text-white font-semibold">{activeJob.processed_count} reports</span> into the system database. All dashboards, triage queues, clusters, and recommendations have been refreshed.
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
            <Link
              to="/"
              className="rounded bg-cyan hover:bg-cyan/90 text-soot px-4 py-2 text-xs font-bold shadow transition"
            >
              View Updated Dashboard
            </Link>
            <Link
              to="/triage"
              className="rounded bg-white/10 hover:bg-white/15 text-white px-4 py-2 text-xs font-medium transition"
            >
              Go to Triage Queue
            </Link>
            <Link
              to="/clusters"
              className="rounded bg-white/10 hover:bg-white/15 text-white px-4 py-2 text-xs font-medium transition"
            >
              Explore Clusters
            </Link>
            <button
              onClick={() => {
                setStep("upload");
                setQualityReport(null);
                setActiveJob(null);
              }}
              className="rounded bg-white/5 hover:bg-white/10 text-ash px-4 py-2 text-xs font-medium transition"
            >
              Ingest Another Batch
            </button>
          </div>
        </div>
      )}

      {/* Historical Ingestion Runs Audit Table */}
      <div className="bg-card border border-white/10 rounded-lg p-6 space-y-4">
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider flex items-center gap-2">
          <span>Ingestion Audit History</span>
          <span className="text-xs text-ash font-normal">({recentJobs.length} past runs)</span>
        </h3>

        {recentJobs.length === 0 ? (
          <p className="text-xs text-ash">No historical ingestion runs found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-white/5 text-ash uppercase font-semibold border-b border-white/10">
                <tr>
                  <th className="p-3">Job ID</th>
                  <th className="p-3">Source Name</th>
                  <th className="p-3">Records Ingested</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {recentJobs.map((job) => (
                  <tr key={job.id} className="hover:bg-white/[0.02]">
                    <td className="p-3 font-mono text-ash">{job.id.slice(0, 8)}...</td>
                    <td className="p-3 text-white font-medium">{job.source}</td>
                    <td className="p-3 text-ash">
                      <span className="text-white font-semibold">{job.processed_count}</span> / {job.record_count}
                    </td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                          job.status === "COMPLETED"
                            ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                            : job.status === "IN_PROGRESS"
                            ? "bg-cyan/20 text-cyan border-cyan/30"
                            : "bg-rose-500/20 text-rose-400 border-rose-500/30"
                        }`}
                      >
                        {job.status}
                      </span>
                    </td>
                    <td className="p-3 text-ash">
                      {new Date(job.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
