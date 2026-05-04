import { Database, FileCheck2, PanelLeftClose, PanelLeftOpen, Settings } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { useEffect, useState } from "react";

export type PageId = "rag" | "review" | "settings";

const nav = [
  { id: "rag", label: "Domains", icon: Database },
  { id: "review", label: "Review files", icon: FileCheck2 },
  { id: "settings", label: "Settings", icon: Settings }
] as const;

export function AppShell({
  page,
  onPageChange,
  children
}: {
  page: PageId;
  onPageChange: (page: PageId) => void;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(() => window.localStorage.getItem("app-shell-collapsed") === "1");

  useEffect(() => {
    window.localStorage.setItem("app-shell-collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  return (
    <div
      className="min-h-screen bg-slate-100 text-slate-950"
      style={{ "--sidebar-width": collapsed ? "5rem" : "16rem" } as CSSProperties}
    >
      <aside
        className={`fixed inset-y-0 left-0 hidden border-r border-slate-200 bg-white transition-[width] duration-200 lg:block ${
          collapsed ? "w-20" : "w-64"
        }`}
      >
        <div className={`border-b border-slate-200 ${collapsed ? "px-3 py-4" : "px-5 py-5"}`}>
          <div className="flex items-center justify-between gap-2">
            {!collapsed && (
              <div className="min-w-0">
                <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">Business Rule AI</div>
                <div className="mt-1 truncate text-xl font-semibold">Operations Console</div>
              </div>
            )}
            <button
              type="button"
              onClick={() => setCollapsed((value) => !value)}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-950"
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
            </button>
          </div>
        </div>
        <nav className={`space-y-1 py-4 ${collapsed ? "px-3" : "px-3"}`}>
          {nav.map((item) => {
            const Icon = item.icon;
            const active = page === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onPageChange(item.id)}
                title={collapsed ? item.label : undefined}
                className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm font-medium ${
                  active ? "bg-slate-950 text-white" : "text-slate-700 hover:bg-slate-100"
                } ${collapsed ? "justify-center" : ""}`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {!collapsed && item.label}
              </button>
            );
          })}
        </nav>
      </aside>
      <main className={collapsed ? "lg:pl-20" : "lg:pl-64"}>
        <div className="border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
          <select
            value={page}
            onChange={(event) => onPageChange(event.target.value as PageId)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            {nav.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        {children}
      </main>
    </div>
  );
}
