import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import client, { formatError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Hexagon, ArrowRight } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await client.post(`/auth/${mode === "login" ? "login" : "register"}`, {
        email,
        password,
      });
      login(data.access_token, data.user);
      toast.success(mode === "login" ? "Access granted" : "Pilot account created");
      navigate("/profile");
    } catch (err) {
      toast.error(formatError(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-[#0B0F17]">
      <div className="hidden lg:flex flex-col justify-between p-12 border-r border-[#243044] grid-bg relative">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0B0F17]/40 to-[#0B0F17]" />
        <div className="relative flex items-center gap-2">
          <Hexagon className="w-7 h-7 text-cyan-400" strokeWidth={2.2} />
          <span className="font-display font-extrabold text-xl">
            Career<span className="text-cyan-400">OS</span>
          </span>
        </div>
        <div className="relative">
          <div className="font-mono text-[11px] tracking-widest uppercase text-cyan-400 mb-3">
            Enterprise Intelligence Workbench
          </div>
          <h2 className="font-display text-4xl font-bold leading-tight tracking-tight max-w-md">
            Verified evidence. Traceable claims. Zero fabrication.
          </h2>
          <p className="text-slate-400 mt-4 max-w-md text-sm leading-relaxed">
            Upload → Verify → Target → Analyze → Match Evidence → Generate → Validate → Review.
            AI proposes, humans verify, code guards the truth.
          </p>
        </div>
        <div className="relative font-mono text-[11px] text-slate-500">
          Canonical Truth · Provenance-First · Isolation Enforced
        </div>
      </div>

      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm animate-in">
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <Hexagon className="w-6 h-6 text-cyan-400" />
            <span className="font-display font-extrabold text-lg">
              Career<span className="text-cyan-400">OS</span>
            </span>
          </div>
          <div className="flex gap-1 p-1 rounded-lg bg-[#141C2B] border border-[#243044] mb-6">
            {["login", "register"].map((m) => (
              <button
                key={m}
                data-testid={`${m === "register" ? "register-tab" : "login-tab"}`}
                onClick={() => setMode(m)}
                className={`flex-1 py-2 rounded-md text-sm font-medium capitalize transition-colors ${
                  mode === m ? "bg-cyan-500/15 text-cyan-300" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {m === "login" ? "Sign in" : "Request pilot"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="font-mono text-[11px] uppercase tracking-widest text-slate-400">Email</label>
              <input
                data-testid="login-email-input"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 w-full bg-[#141C2B] border border-[#243044] rounded-lg px-3 py-2.5 text-sm outline-none focus:border-cyan-500/60 transition-colors"
                placeholder="you@company.com"
              />
            </div>
            <div>
              <label className="font-mono text-[11px] uppercase tracking-widest text-slate-400">Password</label>
              <input
                data-testid="login-password-input"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1.5 w-full bg-[#141C2B] border border-[#243044] rounded-lg px-3 py-2.5 text-sm outline-none focus:border-cyan-500/60 transition-colors"
                placeholder="••••••••"
              />
            </div>
            <button
              data-testid="login-submit-btn"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-cyan-500 hover:bg-cyan-400 text-[#04121a] font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-50"
            >
              {loading ? "Working…" : mode === "login" ? "Enter workbench" : "Create account"}
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
