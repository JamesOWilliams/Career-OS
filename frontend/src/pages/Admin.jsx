import { useEffect, useState } from "react";
import { toast } from "sonner";
import client, { formatError } from "@/lib/api";
import { PageHeader } from "@/components/primitives";
import { UserPlus, Power, PowerOff, X, Loader2 } from "lucide-react";

export default function Admin() {
  const [pilots, setPilots] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", password: "" });
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const { data } = await client.get("/admin/pilots");
      setPilots(data);
    } catch (e) {
      toast.error(formatError(e.response?.data?.detail));
    }
  };
  useEffect(() => {
    load();
  }, []);

  const invite = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await client.post("/admin/pilots/invite", form);
      toast.success("Pilot invited");
      setOpen(false);
      setForm({ email: "", password: "" });
      load();
    } catch (err) {
      toast.error(formatError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (u) => {
    const action = u.status === "disabled" ? "enable" : "disable";
    await client.post(`/admin/pilots/${u.id}/${action}`);
    toast.success(`Pilot ${action}d`);
    load();
  };

  return (
    <div>
      <PageHeader
        eyebrow="Pilot Lifecycle"
        title="Pilot Admin"
        subtitle="Invite, enable and disable pilots. Admin sees usage metadata ONLY — never a user's canonical knowledge, uploads, opportunities or resumes."
      >
        <button
          data-testid="invite-pilot-btn"
          onClick={() => setOpen(true)}
          className="flex items-center gap-2 text-sm px-4 py-2 rounded-lg bg-purple-500 text-white font-semibold hover:bg-purple-400"
        >
          <UserPlus className="w-4 h-4" /> Invite Pilot
        </button>
      </PageHeader>

      <div className="p-8">
        <div className="co-panel overflow-hidden" data-testid="admin-usage-metrics">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#243044] text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                <th className="px-4 py-3">Pilot</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-center">Uploads</th>
                <th className="px-4 py-3 text-center">Verified</th>
                <th className="px-4 py-3 text-center">Opps</th>
                <th className="px-4 py-3 text-center">Resumes</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {pilots.map((u) => (
                <tr key={u.id} className="border-b border-[#1a2436] hover:bg-[#141C2B]/50">
                  <td className="px-4 py-3">{u.email}</td>
                  <td className="px-4 py-3 font-mono text-xs uppercase text-slate-400">{u.role}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`font-mono text-[10px] uppercase px-2 py-0.5 rounded border ${
                        u.status === "disabled"
                          ? "text-rose-400 border-rose-500/40 bg-rose-500/10"
                          : "text-emerald-400 border-emerald-500/40 bg-emerald-500/10"
                      }`}
                    >
                      {u.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center font-mono text-slate-300">{u.usage.uploads}</td>
                  <td className="px-4 py-3 text-center font-mono text-slate-300">{u.usage.verified_nodes}</td>
                  <td className="px-4 py-3 text-center font-mono text-slate-300">{u.usage.opportunities}</td>
                  <td className="px-4 py-3 text-center font-mono text-slate-300">{u.usage.representations}</td>
                  <td className="px-4 py-3 text-right">
                    {u.role !== "admin" && (
                      <button
                        data-testid={`toggle-pilot-${u.id}`}
                        onClick={() => toggle(u)}
                        className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                          u.status === "disabled"
                            ? "text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/10"
                            : "text-rose-300 border-rose-500/40 hover:bg-rose-500/10"
                        }`}
                      >
                        {u.status === "disabled" ? <Power className="w-3.5 h-3.5" /> : <PowerOff className="w-3.5 h-3.5" />}
                        {u.status === "disabled" ? "Enable" : "Disable"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {open && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-6"
          onClick={() => setOpen(false)}
        >
          <div className="co-panel w-full max-w-sm p-6 animate-in" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display font-semibold text-lg">Invite Pilot</h3>
              <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-100">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={invite} className="space-y-4">
              <input
                required
                type="email"
                data-testid="invite-email-input"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="pilot@company.com"
                className="w-full bg-[#0B0F17] border border-[#243044] rounded-lg px-3 py-2 text-sm outline-none focus:border-purple-500/60"
              />
              <input
                required
                type="text"
                data-testid="invite-password-input"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder="temporary password"
                className="w-full bg-[#0B0F17] border border-[#243044] rounded-lg px-3 py-2 text-sm outline-none focus:border-purple-500/60"
              />
              <button
                type="submit"
                disabled={saving}
                data-testid="submit-invite-btn"
                className="w-full flex items-center justify-center gap-2 bg-purple-500 text-white font-semibold py-2.5 rounded-lg hover:bg-purple-400 disabled:opacity-50"
              >
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                Create Pilot
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
