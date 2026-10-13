import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import client, { formatError } from "@/lib/api";
import {
  PageHeader, TierPill, TrackBadge, StrengthBar, WeightBadge,
} from "@/components/primitives";
import {
  ArrowLeft, GitBranch, FileText, ShieldCheck, Loader2, AlertTriangle,
  CheckCircle2, XCircle, Lock, Sparkles, ClipboardList, Download,
} from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

const TABS = [
  { key: "analysis", label: "JD Analysis", icon: ClipboardList },
  { key: "evidence", label: "Evidence Map", icon: GitBranch },
  { key: "representation", label: "Representation", icon: FileText },
  { key: "validation", label: "Validation", icon: ShieldCheck },
];

export default function OpportunityDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState("analysis");
  const [data, setData] = useState(null);
  const [map, setMap] = useState(null);
  const [rep, setRep] = useState(null);
  const [validation, setValidation] = useState(null);
  const [busy, setBusy] = useState("");

  const loadOpp = useCallback(async () => {
    const { data } = await client.get(`/opportunities/${id}`);
    setData(data);
  }, [id]);

  const pollMatching = useCallback(async () => {
    setBusy("match");
    try {
      let status = "running";
      for (let i = 0; i < 120 && status === "running"; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const { data: st } = await client.get(`/opportunities/${id}/match-status`);
        status = st.status;
        if (status === "error") throw new Error(st.error || "Matching failed");
      }
      if (status !== "complete") throw new Error("Matching timed out");
      const m = await client.get(`/opportunities/${id}/evidence-map`);
      setMap(m.data);
      toast.success("Evidence matching complete");
    } catch (e) {
      toast.error(formatError(e.response?.data?.detail) || e.message);
    } finally {
      setBusy("");
    }
  }, [id]);

  const loadAll = useCallback(async () => {
    await loadOpp();
    try {
      const m = await client.get(`/opportunities/${id}/evidence-map`);
      if (m.data.matched) setMap(m.data);
    } catch {}
    try {
      const r = await client.get(`/opportunities/${id}/representation`);
      setRep(r.data);
    } catch {}
    try {
      const v = await client.get(`/opportunities/${id}/validation`);
      setValidation(v.data);
    } catch {}
    // Resume UI state if a matching job is already running (e.g. after a page reload).
    try {
      const st = await client.get(`/opportunities/${id}/match-status`);
      if (st.data.status === "running") {
        setTab("evidence");
        pollMatching();
      }
    } catch {}
  }, [id, loadOpp, pollMatching]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const runMatch = async () => {
    setBusy("match");
    setTab("evidence");
    try {
      await client.post(`/opportunities/${id}/match`);
    } catch (e) {
      setBusy("");
      toast.error(formatError(e.response?.data?.detail) || e.message);
      return;
    }
    // Matching runs as a background job; poll status to avoid a long-lived request.
    await pollMatching();
  };

  const runGenerate = async () => {
    setBusy("generate");
    try {
      const { data: r } = await client.post(`/opportunities/${id}/generate`);
      setRep(r);
      toast.success("Resume generated from verified evidence");
      setTab("representation");
    } catch (e) {
      const d = e.response?.data?.detail;
      toast.error(typeof d === "object" ? "Generation blocked — check preflight" : formatError(d));
    } finally {
      setBusy("");
    }
  };

  const runValidate = async () => {
    setBusy("validate");
    try {
      const { data: v } = await client.post(`/opportunities/${id}/validate`);
      setValidation(v);
      toast[v.passed ? "success" : "warning"](
        v.passed ? "All contract gates passed" : "Some gates need attention"
      );
      setTab("validation");
    } catch (e) {
      toast.error(formatError(e.response?.data?.detail));
    } finally {
      setBusy("");
    }
  };

  const exportResume = async (fmt) => {
    try {
      const res = await client.get(`/opportunities/${id}/export?format=${fmt}`, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      const cd = res.headers["content-disposition"] || "";
      const match = cd.match(/filename="?([^"]+)"?/);
      a.download = match ? match[1] : `resume.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success(`Exported ${fmt.toUpperCase()}`);
    } catch (e) {
      // 409 identity-incomplete arrives as a blob; parse it for a clear remediation message.
      let detail = e.response?.data;
      if (detail instanceof Blob) {
        try { detail = JSON.parse(await detail.text()).detail; } catch { detail = null; }
      } else {
        detail = detail?.detail;
      }
      if (detail?.reason === "identity_incomplete") {
        toast.error(
          `Add ${detail.missing.join(", ")} in Career Profile → Identity & Contact, then regenerate.`,
          { duration: 8000 }
        );
      } else {
        toast.error("Export failed");
      }
    }
  };

  if (!data)
    return <div className="p-8 text-slate-500 font-mono text-sm">Loading opportunity…</div>;

  const { opportunity, requirements, preflight } = data;
  const blocked = preflight.status === "BLOCKED";

  return (
    <div>
      <PageHeader
        eyebrow={opportunity.organization || "Target Engagement"}
        title={opportunity.target_role}
        subtitle={`${requirements.length} requirements · ${preflight.status === "READY" ? "runtime ready" : "runtime BLOCKED"}`}
      >
        <button
          onClick={() => navigate("/opportunities")}
          className="flex items-center gap-2 text-sm px-3 py-2 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-[#1A2436]"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
      </PageHeader>

      <div className="px-8 pt-5">
        {blocked && (
          <div className="gap-callout rounded-xl p-4 mb-4 flex items-start gap-3" data-testid="preflight-blocked">
            <Lock className="w-5 h-5 text-rose-400 mt-0.5" />
            <div>
              <div className="font-semibold text-rose-300">Runtime preflight BLOCKED (fail-closed)</div>
              <div className="text-sm text-slate-400 mt-1">
                Missing: {preflight.missing.join(", ")}. Generation is disabled until resolved.
                {preflight.missing.includes("verified_evidence") && " Verify canonical nodes in Career Profile."}
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 mb-4">
          <button
            data-testid="run-matching-btn"
            onClick={runMatch}
            disabled={busy || blocked}
            className="flex items-center gap-2 text-sm px-4 py-2 rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/25 disabled:opacity-40"
          >
            {busy === "match" ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitBranch className="w-4 h-4" />}
            Run Evidence Matching
          </button>
          <button
            data-testid="generate-resume-btn"
            onClick={runGenerate}
            disabled={busy || blocked || !map}
            className="flex items-center gap-2 text-sm px-4 py-2 rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/25 disabled:opacity-40"
          >
            {busy === "generate" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            Generate Resume
          </button>
          <button
            data-testid="run-validation-btn"
            onClick={runValidate}
            disabled={busy || !rep}
            className="flex items-center gap-2 text-sm px-4 py-2 rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/25 disabled:opacity-40"
          >
            {busy === "validate" ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
            Run Validation
          </button>
        </div>

        <div className="flex gap-1 border-b border-[#243044]">
          {TABS.map((t) => (
            <button
              key={t.key}
              data-testid={`tab-${t.key}`}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === t.key
                  ? "border-cyan-400 text-cyan-300"
                  : "border-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              <t.icon className="w-4 h-4" /> {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="p-8 pt-6">
        {tab === "analysis" && <Analysis requirements={requirements} jd={opportunity.job_description} />}
        {tab === "evidence" && <EvidenceMap map={map} busy={busy === "match"} />}
        {tab === "representation" && <Representation rep={rep} onExport={exportResume} />}
        {tab === "validation" && <Validation validation={validation} />}
      </div>
    </div>
  );
}

function Analysis({ requirements, jd }) {
  if (!requirements.length)
    return <div className="text-slate-500">No requirements extracted.</div>;
  const byTier = [1, 2, 3, 4].map((t) => ({ tier: t, items: requirements.filter((r) => r.tier === t) }));
  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-4">
        {byTier.map(
          (g) =>
            g.items.length > 0 && (
              <div key={g.tier} data-testid={`requirement-tier-${g.tier}-list`}>
                <div className="flex items-center gap-2 mb-2">
                  <TierPill tier={g.tier} />
                  <span className="text-xs text-slate-500 font-mono">{g.items.length} requirement(s)</span>
                </div>
                <div className="space-y-2">
                  {g.items.map((r) => (
                    <div key={r.id} className="co-panel p-3 flex items-start gap-3">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-slate-500 mt-0.5 shrink-0">
                        {r.category?.replace(/_/g, " ")}
                      </span>
                      <span className="text-sm text-slate-200">{r.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            )
        )}
      </div>
      <div className="co-panel p-4 h-fit">
        <div className="font-mono text-[10px] uppercase tracking-widest text-slate-400 mb-2">Job Description</div>
        <p className="text-xs text-slate-400 whitespace-pre-wrap leading-relaxed max-h-[60vh] overflow-y-auto">{jd}</p>
      </div>
    </div>
  );
}

function EvidenceMap({ map, busy }) {
  if (busy)
    return (
      <div className="co-panel p-10 text-center text-cyan-300 flex flex-col items-center gap-3">
        <Loader2 className="w-7 h-7 animate-spin" />
        <span className="font-mono text-sm">Retrieving verified evidence & scoring matches…</span>
      </div>
    );
  if (!map)
    return (
      <div className="co-panel p-10 text-center text-slate-400">
        Run <span className="text-cyan-400">Evidence Matching</span> to build the map: requirement → evidence → strength → weight → provenance.
      </div>
    );
  return (
    <div data-testid="evidence-map-table">
      <div className="flex gap-4 mb-4 font-mono text-xs">
        <span className="text-slate-400">TOTAL {map.summary.total}</span>
        <span className="text-emerald-400">COVERED {map.summary.covered}</span>
        <span className="text-rose-400">GAPS {map.summary.gaps}</span>
      </div>
      <div className="space-y-3">
        {map.rows.map((row) => (
          <div
            key={row.requirement.id}
            className={`rounded-xl p-4 ${row.gap ? "gap-callout" : "co-panel"} animate-in`}
          >
            <div className="flex items-start justify-between gap-3 mb-3">
              <div className="flex items-start gap-2">
                <TierPill tier={row.requirement.tier} />
                <span className="text-sm font-medium text-slate-100">{row.requirement.text}</span>
              </div>
            </div>
            {row.gap ? (
              <div className="flex items-center gap-2 text-sm text-rose-300" data-testid="evidence-gap-alert-item">
                <AlertTriangle className="w-4 h-4" />
                No sufficient canonical evidence — requirement left unclaimed (uncertainty preserved).
              </div>
            ) : (
              <div className="space-y-2">
                {row.matches.map((m) => (
                  <div key={m.id} className="bg-[#0B0F17] border border-[#243044] rounded-lg p-3">
                    <div className="grid md:grid-cols-5 gap-3 items-center">
                      <div className="md:col-span-2">
                        <div className="text-sm font-medium">{m.identity?.role}</div>
                        <div className="text-xs text-slate-400">
                          {m.track === "intellectual_property" ? m.identity?.organization : m.identity?.employer}
                        </div>
                        <div className="font-mono text-[10px] text-slate-500 mt-0.5">{m.source_experience}</div>
                      </div>
                      <div>
                        <TrackBadge track={m.track} />
                      </div>
                      <div data-testid="match-strength-indicator">
                        <StrengthBar value={m.match_strength} />
                      </div>
                      <div className="flex justify-end">
                        <WeightBadge weight={m.representation_weight} />
                      </div>
                    </div>
                    {m.provenance?.rationale && (
                      <div className="text-xs text-slate-500 mt-2 italic border-t border-[#1a2436] pt-2">
                        ▸ {m.provenance.rationale}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function EvidenceIndicator({ exp, nodeIds }) {
  const ids = (nodeIds || []).filter(Boolean);
  const src = exp.track === "intellectual_property" ? exp.organization : exp.employer;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          data-testid="claim-trace-badge"
          title="Inspect canonical evidence"
          className="ml-2 inline-flex items-center gap-1 align-middle rounded px-1.5 py-0.5 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 transition-colors"
        >
          <ShieldCheck className="w-3 h-3" />
          <span className="font-mono text-[9px] uppercase tracking-wider">Evidence</span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="w-72 bg-[#141C2B] border-[#243044] text-slate-200"
        data-testid="evidence-provenance-popover"
      >
        <div className="space-y-2">
          <div className="font-mono text-[10px] uppercase tracking-widest text-cyan-400">
            Canonical Evidence
          </div>
          <div className="text-xs">
            <span className="text-slate-500">
              {ids.length > 1 ? "Source nodes:" : "Node ID:"}
            </span>{" "}
            <span className="font-mono text-slate-200">{ids.join(", ")}</span>
          </div>
          <div className="text-xs">
            <span className="text-slate-500">Verified source:</span>{" "}
            <span className="text-slate-200">
              {exp.role || "—"}
              {src ? ` · ${src}` : ""}
            </span>
          </div>
          {exp.client && (
            <div className="text-xs">
              <span className="text-slate-500">Client:</span>{" "}
              <span className="text-purple-300">{exp.client}</span>
            </div>
          )}
          <div className="flex items-center gap-1.5 text-xs text-emerald-400">
            <CheckCircle2 className="w-3.5 h-3.5" />{" "}
            {ids.length > 1 ? `${ids.length} VERIFIED canonical nodes` : "VERIFIED canonical node"}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function Representation({ rep, onExport }) {
  if (!rep)
    return (
      <div className="co-panel p-10 text-center text-slate-500">
        No representation yet. Run <span className="text-cyan-400">Generate Resume</span> after evidence matching.
      </div>
    );
  const s = rep.sections;
  const CATS = [
    ["experience", "Experience"],
    ["military", "Military Service"],
    ["projects", "Independent Projects"],
  ];
  const catOf = (e) =>
    e.category ||
    (e.track === "intellectual_property"
      ? "projects"
      : e.track === "military"
      ? "military"
      : "experience");
  return (
    <div className="max-w-3xl mx-auto" data-testid="resume-preview-container">
      <div className="flex items-center justify-end gap-2 mb-3">
        <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500 mr-auto">
          Export Resume v{rep.template_version}
        </span>
        <button
          data-testid="export-resume-pdf-btn"
          onClick={() => onExport && onExport("pdf")}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/25 transition-colors"
        >
          <Download className="w-3.5 h-3.5" /> PDF
        </button>
        <button
          data-testid="export-resume-docx-btn"
          onClick={() => onExport && onExport("docx")}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/25 transition-colors"
        >
          <Download className="w-3.5 h-3.5" /> DOCX
        </button>
      </div>
      <div className="bg-[#0F1622] border border-[#243044] rounded-xl p-8 space-y-6">
        {rep.identity_stale && (
          <div
            data-testid="identity-stale-banner"
            className="flex items-start gap-2 text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>
              This resume uses an older identity snapshot. Your Identity &amp; Contact details have
              changed since it was generated — click <span className="text-cyan-300">Generate Resume</span> to refresh it.
            </span>
          </div>
        )}
        {s.identity && (s.identity.full_name || s.identity.email || s.identity.phone) && (
          <div className="border-b border-[#243044] pb-4" data-testid="resume-identity-header">
            <div className="font-display font-bold text-2xl text-slate-50">{s.identity.full_name}</div>
            <div className="text-sm text-slate-400 mt-1">
              {[s.identity.email, formatPhone(s.identity.phone), s.identity.location].filter(Boolean).join("  ·  ")}
            </div>
            {(s.identity.links || []).length > 0 && (
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5">
                {s.identity.links.map((l, i) => (
                  <a
                    key={i}
                    data-testid={`resume-identity-link-${i}`}
                    href={l.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-cyan-400 hover:text-cyan-300 underline underline-offset-2"
                  >
                    {l.label || l.url}
                  </a>
                ))}
              </div>
            )}
          </div>
        )}
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-cyan-400 mb-2">Professional Summary</div>
          <p className="text-sm text-slate-200 leading-relaxed">{s.summary}</p>
        </div>
        {CATS.map(([cat, label]) => {
          const items = s.experiences.filter((e) => catOf(e) === cat);
          if (!items.length) return null;
          return (
            <div key={cat} className="space-y-5" data-testid={`resume-category-${cat}`}>
              <div className="font-mono text-[10px] uppercase tracking-widest text-cyan-400">{label}</div>
              {items.map((e) => <ExperienceEntry key={e.node_id} e={e} />)}
            </div>
          );
        })}
        <div className="border-t border-[#243044] pt-3 font-mono text-[10px] text-slate-500">
          Template v{rep.template_version} · Contract v{rep.contract_version} · {rep.claim_provenance.length} traceable claims
        </div>
      </div>
    </div>
  );
}

function formatPhone(raw) {
  const digits = (raw || "").replace(/\D/g, "");
  if (digits.length === 10) return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  if (digits.length === 11 && digits[0] === "1")
    return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  return raw || "";
}

function ExperienceEntry({ e }) {
  const isIP = e.track === "intellectual_property";
  const projectName = (e.organization || "").trim();
  const title = isIP ? projectName || "Independent Project" : e.role || e.employer || "Experience";
  const subtitle = isIP ? e.role : e.employer;
  const dates = e.display_dates != null ? e.display_dates : `${e.start} – ${e.end}`;
  return (
    <div className="border-l-2 border-[#243044] pl-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="font-display font-semibold text-slate-100">{title}</div>
          {(subtitle || e.client) && (
            <div className="text-sm text-slate-400">
              {subtitle}
              {e.client && <span className="text-purple-300">{subtitle ? " · " : ""}client: {e.client}</span>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <TrackBadge track={e.track} />
          <span className="font-mono text-[10px] text-slate-500">{dates}</span>
        </div>
      </div>
      <ul className="mt-2 space-y-1.5">
        {e.bullets.map((b, i) => (
          <li key={i} className="text-sm text-slate-300 flex gap-2 group">
            <span className="text-cyan-500 mt-1">▸</span>
            <span>
              {b.text}
              <EvidenceIndicator exp={e} nodeIds={b.source_node_ids || [b.source_node_id]} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const GATE_LABELS = {
  canonical_truth: "Canonical Truth",
  evidence: "Evidence",
  metric_integrity: "Metric Integrity",
  chronology: "Chronology",
  relationship_integrity: "Relationship Integrity",
  jd_relevance: "JD Relevance",
  removal: "Removal / Uncertainty",
  ats_readability: "ATS & Readability",
  compression: "Compression",
  interview_defense: "Interview Defense",
};

function Validation({ validation }) {
  if (!validation)
    return (
      <div className="co-panel p-10 text-center text-slate-500">
        No validation run yet. Generate a resume, then run <span className="text-cyan-400">Validation</span>.
      </div>
    );
  const gates = validation.gate_results;
  return (
    <div>
      <div
        data-testid="validation-gate-status"
        className={`rounded-xl p-5 mb-5 flex items-center gap-3 ${
          validation.passed ? "node-verified" : "gap-callout"
        }`}
      >
        {validation.passed ? (
          <CheckCircle2 className="w-6 h-6 text-emerald-400" />
        ) : (
          <AlertTriangle className="w-6 h-6 text-rose-400" />
        )}
        <div>
          <div className="font-display font-semibold text-lg">
            {validation.passed ? "Resume Contract: PASSED" : "Resume Contract: NEEDS REVIEW"}
          </div>
          <div className="text-sm text-slate-400">
            {validation.passed
              ? "All quality gates satisfied — ready for human review."
              : "One or more gates failed. Resolve before human signoff."}
          </div>
        </div>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        {Object.entries(gates).map(([key, g]) => (
          <div key={key} data-testid={`validation-gate-${key}`} className="co-panel p-4 flex items-start gap-3">
            {g.status === "pass" ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-400 mt-0.5 shrink-0" />
            ) : g.status === "warn" ? (
              <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5 shrink-0" />
            ) : (
              <XCircle className="w-5 h-5 text-rose-400 mt-0.5 shrink-0" />
            )}
            <div>
              <div className="font-medium text-sm flex items-center gap-2">
                {GATE_LABELS[key] || key}
                <span
                  className={`font-mono text-[9px] uppercase px-1.5 py-0.5 rounded ${
                    g.status === "pass"
                      ? "text-emerald-400 bg-emerald-500/10"
                      : g.status === "warn"
                      ? "text-amber-400 bg-amber-500/10"
                      : "text-rose-400 bg-rose-500/10"
                  }`}
                >
                  {g.status}
                </span>
              </div>
              <div className="text-xs text-slate-400 mt-1">{g.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
