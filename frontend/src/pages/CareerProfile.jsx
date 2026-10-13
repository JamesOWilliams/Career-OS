import { useEffect, useState } from "react";
import { toast } from "sonner";
import client, { formatError } from "@/lib/api";
import { PageHeader, TrackBadge, StateBadge } from "@/components/primitives";
import { CheckCircle2, Trash2, ShieldCheck, Pencil, X, Save } from "lucide-react";

const TRACKS = [
  { key: "all", label: "All" },
  { key: "civilian", label: "Civilian", testid: "profile-track-tab-civilian" },
  { key: "military", label: "Military", testid: "profile-track-tab-military" },
  { key: "intellectual_property", label: "Intellectual Property", testid: "profile-track-tab-ip" },
];

export default function CareerProfile() {
  const [nodes, setNodes] = useState([]);
  const [track, setTrack] = useState("all");
  const [stateFilter, setStateFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [profile, setProfile] = useState(null);
  const [savingProfile, setSavingProfile] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await client.get("/career/nodes");
      setNodes(data);
    } catch (e) {
      toast.error(formatError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };
  const loadProfile = async () => {
    try {
      const { data } = await client.get("/profile");
      setProfile({ links: [], ...data });
    } catch (e) {
      setProfile({ full_name: "", email: "", phone: "", location: "", links: [] });
    }
  };
  useEffect(() => {
    load();
    loadProfile();
  }, []);

  const filtered = nodes.filter(
    (n) => (track === "all" || n.track === track) && (stateFilter === "all" || n.state === stateFilter)
  );

  const verify = async (id) => {
    await client.post(`/career/nodes/${id}/verify`);
    toast.success("Node promoted to VERIFIED");
    load();
  };
  const reject = async (id) => {
    await client.post(`/career/nodes/${id}/reject`);
    toast.success("Proposal rejected");
    load();
  };
  const saveEdit = async () => {
    try {
      await client.patch(`/career/nodes/${editing.id}`, {
        identity: editing.identity,
        evidence: editing.evidence,
        context: editing.context,
      });
      toast.success("Node updated — returned to PROPOSED for re-verification");
      setEditing(null);
      load();
    } catch (e) {
      toast.error(formatError(e.response?.data?.detail));
    }
  };

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      const payload = {
        full_name: profile.full_name || "",
        email: profile.email || "",
        phone: profile.phone || "",
        location: profile.location || "",
        links: (profile.links || []).filter((l) => (l.url || "").trim()),
      };
      const { data } = await client.put("/profile", payload);
      setProfile({ links: [], ...data });
      toast.success("Identity & contact saved");
    } catch (e) {
      toast.error(formatError(e.response?.data?.detail));
    } finally {
      setSavingProfile(false);
    }
  };

  const counts = {
    verified: nodes.filter((n) => n.state === "VERIFIED").length,
    proposed: nodes.filter((n) => n.state === "PROPOSED").length,
  };

  return (
    <div>
      <PageHeader
        eyebrow="Canonical Knowledge Base"
        title="Career Profile"
        subtitle="PROPOSED nodes (amber, dashed) are AI-extracted and not yet usable as final claims. Promote to VERIFIED (emerald) to make them canonical."
      >
        <div className="flex gap-3 font-mono text-xs">
          <span className="text-emerald-400" data-testid="verified-count">{counts.verified} VERIFIED</span>
          <span className="text-amber-400" data-testid="proposed-count">{counts.proposed} PROPOSED</span>
        </div>
      </PageHeader>

      <div className="p-8 space-y-5">
        <IdentityPanel
          profile={profile}
          setProfile={setProfile}
          onSave={saveProfile}
          saving={savingProfile}
        />
        <div className="flex flex-wrap items-center gap-2">
          {TRACKS.map((t) => (
            <button
              key={t.key}
              data-testid={t.testid}
              onClick={() => setTrack(t.key)}
              className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                track === t.key
                  ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/40"
                  : "text-slate-400 border-[#243044] hover:text-slate-200"
              }`}
            >
              {t.label}
            </button>
          ))}
          <div className="w-px h-6 bg-[#243044] mx-1" />
          {["all", "PROPOSED", "VERIFIED"].map((s) => (
            <button
              key={s}
              onClick={() => setStateFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono uppercase border transition-colors ${
                stateFilter === s
                  ? "bg-[#1A2436] text-slate-100 border-[#31425c]"
                  : "text-slate-500 border-[#243044] hover:text-slate-300"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-slate-500 font-mono text-sm">Loading canonical nodes…</div>
        ) : filtered.length === 0 ? (
          <div className="co-panel p-10 text-center text-slate-500">
            No nodes here yet. Upload a resume in <span className="text-cyan-400">Resume Ingestion</span> to extract proposals.
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {filtered.map((n) => (
              <div
                key={n.id}
                data-testid={`node-card-${n.node_id}`}
                className={`rounded-xl p-5 animate-in ${n.state === "VERIFIED" ? "node-verified" : "node-proposed"}`}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div>
                    <div className="font-display font-semibold text-base">
                      {n.identity?.role || "Untitled role"}
                    </div>
                    <div className="text-sm text-slate-400">
                      {n.track === "intellectual_property"
                        ? n.identity?.organization
                        : n.identity?.employer}
                      {n.identity?.client && (
                        <span className="text-purple-300"> · client: {n.identity.client}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    <StateBadge state={n.state} />
                    <TrackBadge track={n.track} />
                  </div>
                </div>
                <div className="font-mono text-[10px] text-slate-500 mb-2">
                  {n.node_id} · {n.identity?.start} – {n.identity?.end || "—"}
                </div>
                <ul className="space-y-1 mb-3">
                  {(n.evidence || []).slice(0, 3).map((e, i) => (
                    <li key={i} className="text-xs text-slate-300 flex gap-2">
                      <span className="text-cyan-500 mt-0.5">▸</span>
                      <span>{e}</span>
                    </li>
                  ))}
                </ul>
                {(n.retrieval?.metrics || []).length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-3">
                    {n.retrieval.metrics.map((m, i) => (
                      <span key={i} className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
                        {m}
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                  {n.state === "PROPOSED" && (
                    <button
                      data-testid={`verify-node-btn-${n.node_id}`}
                      onClick={() => verify(n.id)}
                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/25 transition-colors"
                    >
                      <ShieldCheck className="w-3.5 h-3.5" /> Verify
                    </button>
                  )}
                  {n.state === "VERIFIED" && (
                    <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Canonical
                    </span>
                  )}
                  <button
                    onClick={() => setEditing({ ...n })}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-[#1A2436] transition-colors"
                  >
                    <Pencil className="w-3.5 h-3.5" /> Edit
                  </button>
                  <button
                    data-testid={`reject-node-btn-${n.node_id}`}
                    onClick={() => reject(n.id)}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg text-slate-400 hover:text-rose-300 hover:bg-rose-500/10 transition-colors ml-auto"
                  >
                    <Trash2 className="w-3.5 h-3.5" /> {n.state === "PROPOSED" ? "Reject" : "Remove"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {editing && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-6"
          onClick={() => setEditing(null)}
        >
          <div className="co-panel w-full max-w-lg p-6 animate-in max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display font-semibold text-lg">Edit node · {editing.node_id}</h3>
              <button onClick={() => setEditing(null)} className="text-slate-400 hover:text-slate-100">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3">
              {["role", "employer", "organization", "client", "start", "end"].map((f) => (
                <div key={f}>
                  <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400">{f}</label>
                  <input
                    value={editing.identity?.[f] || ""}
                    onChange={(e) =>
                      setEditing({ ...editing, identity: { ...editing.identity, [f]: e.target.value } })
                    }
                    className="mt-1 w-full bg-[#0B0F17] border border-[#243044] rounded-lg px-3 py-2 text-sm outline-none focus:border-cyan-500/60"
                  />
                </div>
              ))}
              <div>
                <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400">Evidence (one per line)</label>
                <textarea
                  rows={5}
                  value={(editing.evidence || []).join("\n")}
                  onChange={(e) => setEditing({ ...editing, evidence: e.target.value.split("\n").filter(Boolean) })}
                  className="mt-1 w-full bg-[#0B0F17] border border-[#243044] rounded-lg px-3 py-2 text-sm outline-none focus:border-cyan-500/60"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setEditing(null)} className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-100">
                Cancel
              </button>
              <button
                data-testid="save-node-edit-btn"
                onClick={saveEdit}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-cyan-500 text-[#04121a] font-semibold hover:bg-cyan-400"
              >
                <Save className="w-4 h-4" /> Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const LINK_LABELS = ["LinkedIn", "GitHub", "Portfolio", "Website", "Other"];

function IdentityPanel({ profile, setProfile, onSave, saving }) {
  if (!profile) return null;
  const setField = (k, v) => setProfile({ ...profile, [k]: v });
  const links = profile.links || [];
  const setLink = (i, patch) => {
    const next = links.map((l, idx) => (idx === i ? { ...l, ...patch } : l));
    setProfile({ ...profile, links: next });
  };
  const addLink = () => setProfile({ ...profile, links: [...links, { label: "LinkedIn", url: "" }] });
  const removeLink = (i) => setProfile({ ...profile, links: links.filter((_, idx) => idx !== i) });

  const FIELDS = [
    ["full_name", "Full name", "Jane A. Candidate"],
    ["email", "Professional email", "jane@domain.com"],
    ["phone", "Phone", "+1 555 000 0000"],
    ["location", "Location", "San Antonio, TX"],
  ];

  return (
    <div className="co-panel p-6 space-y-4" data-testid="identity-contact-panel">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-display font-semibold text-base text-slate-100">Identity &amp; Contact</div>
          <div className="text-xs text-slate-500 mt-0.5">
            Appears at the top of generated resumes. Separate from canonical career evidence. Enter
            your professional email explicitly — it is never taken from your login.
          </div>
        </div>
        <button
          data-testid="save-identity-btn"
          onClick={onSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-cyan-500 text-[#04121a] font-semibold hover:bg-cyan-400 disabled:opacity-50"
        >
          <Save className="w-4 h-4" /> {saving ? "Saving…" : "Save"}
        </button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {FIELDS.map(([k, label, ph]) => (
          <div key={k}>
            <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400">{label}</label>
            <input
              data-testid={`identity-${k}-input`}
              value={profile[k] || ""}
              placeholder={ph}
              onChange={(e) => setField(k, e.target.value)}
              className="mt-1 w-full bg-[#0B0F17] border border-[#243044] rounded-lg px-3 py-2 text-sm outline-none focus:border-cyan-500/60"
            />
          </div>
        ))}
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400">
            Professional links (HTTPS only)
          </label>
          <button
            data-testid="add-link-btn"
            onClick={addLink}
            className="text-xs px-2 py-1 rounded-lg text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/15"
          >
            + Add link
          </button>
        </div>
        {links.map((l, i) => (
          <div key={i} className="flex gap-2 items-center">
            <select
              data-testid={`link-label-${i}`}
              value={l.label || "Other"}
              onChange={(e) => setLink(i, { label: e.target.value })}
              className="bg-[#0B0F17] border border-[#243044] rounded-lg px-2 py-2 text-sm outline-none focus:border-cyan-500/60"
            >
              {LINK_LABELS.map((x) => (
                <option key={x} value={x}>{x}</option>
              ))}
            </select>
            <input
              data-testid={`link-url-${i}`}
              value={l.url || ""}
              placeholder="https://…"
              onChange={(e) => setLink(i, { url: e.target.value })}
              className="flex-1 bg-[#0B0F17] border border-[#243044] rounded-lg px-3 py-2 text-sm outline-none focus:border-cyan-500/60"
            />
            <button
              data-testid={`remove-link-${i}`}
              onClick={() => removeLink(i)}
              className="text-slate-400 hover:text-rose-300 p-2"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

