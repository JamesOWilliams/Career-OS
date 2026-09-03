import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import client, { formatError } from "@/lib/api";
import { PageHeader } from "@/components/primitives";
import { Plus, Target, ArrowRight, Loader2, X } from "lucide-react";

export default function Opportunities() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ target_role: "", organization: "", job_description: "" });

  const load = async () => {
    const { data } = await client.get("/opportunities");
    setItems(data);
  };
  useEffect(() => {
    load();
  }, []);

  const create = async (e) => {
    e.preventDefault();
    if (!form.job_description.trim()) {
      toast.error("Job description is required");
      return;
    }
    setSaving(true);
    try {
      const { data } = await client.post("/opportunities", form);
      toast.success("Opportunity created & JD analyzed");
      setOpen(false);
      setForm({ target_role: "", organization: "", job_description: "" });
      navigate(`/opportunities/${data.id}`);
    } catch (err) {
      toast.error(formatError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Target Engagements"
        title="Opportunities"
        subtitle="Define a target role with its job description. Career OS decomposes the JD into tiered requirements to drive evidence matching."
      >
        <button
          data-testid="new-opportunity-btn"
          onClick={() => setOpen(true)}
          className="flex items-center gap-2 text-sm px-4 py-2 rounded-lg bg-cyan-500 text-[#04121a] font-semibold hover:bg-cyan-400"
        >
          <Plus className="w-4 h-4" /> New Opportunity
        </button>
      </PageHeader>

      <div className="p-8">
        {items.length === 0 ? (
          <div className="co-panel p-10 text-center text-slate-500">
            No opportunities yet. Create one to begin the analysis loop.
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {items.map((o) => (
              <button
                key={o.id}
                data-testid={`opportunity-card-${o.id}`}
                onClick={() => navigate(`/opportunities/${o.id}`)}
                className="co-panel p-5 text-left hover:border-cyan-500/40 transition-colors group animate-in"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
                    <Target className="w-4 h-4 text-cyan-400" />
                  </div>
                  <ArrowRight className="w-4 h-4 text-slate-600 group-hover:text-cyan-400 transition-colors" />
                </div>
                <div className="font-display font-semibold">{o.target_role}</div>
                <div className="text-sm text-slate-400">{o.organization || "—"}</div>
                <p className="text-xs text-slate-500 mt-3 line-clamp-2">{o.job_description}</p>
              </button>
            ))}
          </div>
        )}
      </div>

      {open && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-6"
          onClick={() => setOpen(false)}
        >
          <div className="co-panel w-full max-w-xl p-6 animate-in max-h-[88vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display font-semibold text-lg">New Opportunity</h3>
              <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-100">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={create} className="space-y-4">
              <div>
                <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400">Target role *</label>
                <input
                  required
                  data-testid="opportunity-role-input"
                  value={form.target_role}
                  onChange={(e) => setForm({ ...form, target_role: e.target.value })}
                  className="mt-1 w-full bg-[#0B0F17] border border-[#243044] rounded-lg px-3 py-2 text-sm outline-none focus:border-cyan-500/60"
                  placeholder="Director of Product Management"
                />
              </div>
              <div>
                <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400">Organization</label>
                <input
                  data-testid="opportunity-org-input"
                  value={form.organization}
                  onChange={(e) => setForm({ ...form, organization: e.target.value })}
                  className="mt-1 w-full bg-[#0B0F17] border border-[#243044] rounded-lg px-3 py-2 text-sm outline-none focus:border-cyan-500/60"
                  placeholder="Allstate"
                />
              </div>
              <div>
                <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400">Job description *</label>
                <textarea
                  required
                  rows={8}
                  data-testid="opportunity-jd-textarea"
                  value={form.job_description}
                  onChange={(e) => setForm({ ...form, job_description: e.target.value })}
                  className="mt-1 w-full bg-[#0B0F17] border border-[#243044] rounded-lg px-3 py-2 text-sm outline-none focus:border-cyan-500/60"
                  placeholder="Paste the full job description…"
                />
              </div>
              <button
                type="submit"
                data-testid="analyze-jd-btn"
                disabled={saving}
                className="w-full flex items-center justify-center gap-2 bg-cyan-500 text-[#04121a] font-semibold py-2.5 rounded-lg hover:bg-cyan-400 disabled:opacity-50"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {saving ? "Analyzing JD…" : "Create & Analyze"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
