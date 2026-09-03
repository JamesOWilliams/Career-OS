import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  Layers, UploadCloud, Target, ShieldCheck, LogOut, Hexagon, Users,
} from "lucide-react";

const nav = [
  { to: "/profile", label: "Career Profile", icon: Layers, id: "nav-profile" },
  { to: "/upload", label: "Resume Ingestion", icon: UploadCloud, id: "nav-upload" },
  { to: "/opportunities", label: "Opportunities", icon: Target, id: "nav-opportunities" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex bg-[#0B0F17] text-slate-100">
      <aside className="w-64 shrink-0 bg-[#0E1420] border-r border-[#243044] h-screen sticky top-0 flex flex-col justify-between p-4">
        <div>
          <div className="flex items-center gap-2 px-2 py-3 mb-4">
            <Hexagon className="w-6 h-6 text-cyan-400" strokeWidth={2.2} />
            <div>
              <div className="font-display font-extrabold text-lg leading-none tracking-tight">
                Career<span className="text-cyan-400">OS</span>
              </div>
              <div className="font-mono text-[10px] tracking-widest text-slate-500 uppercase mt-0.5">
                Intelligence Workbench
              </div>
            </div>
          </div>
          <nav className="space-y-1">
            {nav.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                data-testid={n.id}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/30"
                      : "text-slate-400 hover:text-slate-100 hover:bg-[#141C2B] border border-transparent"
                  }`
                }
              >
                <n.icon className="w-4 h-4" />
                {n.label}
              </NavLink>
            ))}
            {user?.role === "admin" && (
              <NavLink
                to="/admin"
                data-testid="nav-admin"
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-purple-500/10 text-purple-300 border border-purple-500/30"
                      : "text-slate-400 hover:text-slate-100 hover:bg-[#141C2B] border border-transparent"
                  }`
                }
              >
                <Users className="w-4 h-4" />
                Pilot Admin
              </NavLink>
            )}
          </nav>
        </div>

        <div className="border-t border-[#243044] pt-3">
          <div className="flex items-center gap-2 px-2 mb-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <div className="min-w-0">
              <div className="text-xs text-slate-300 truncate" data-testid="current-user-email">
                {user?.email}
              </div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
                {user?.role}
              </div>
            </div>
          </div>
          <button
            data-testid="logout-btn"
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-rose-300 hover:bg-rose-500/10 transition-colors"
          >
            <LogOut className="w-4 h-4" /> Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto h-screen">
        <Outlet />
      </main>
    </div>
  );
}
