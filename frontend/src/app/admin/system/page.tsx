"use client";
import { useEffect, useState } from "react";
import { RefreshCw, Users, Zap, AlertTriangle, Activity, Server, DollarSign, Clock, TrendingUp } from "lucide-react";
import { adminApi, SystemSummary, AuditLogRow } from "@/lib/api";
import StatCard from "@/components/admin/StatCard";
import DataTable, { ColDef } from "@/components/admin/DataTable";

function fmtTs(ts: string) {
  return new Date(ts).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

function actionColor(action: string) {
  if (action.includes("delete"))    return "text-red-400";
  if (action.includes("suspend"))   return "text-amber-400";
  if (action.includes("reset"))     return "text-amber-400";
  if (action.includes("update"))    return "text-blue-400";
  return "text-zinc-400";
}

export default function AdminSystemPage() {
  const [summary, setSummary] = useState<SystemSummary | null>(null);
  const [logs,    setLogs]    = useState<AuditLogRow[]>([]);
  const [logTotal, setLogTotal] = useState(0);
  const [logPage,  setLogPage]  = useState(0);
  const [loading,  setLoading]  = useState(true);
  const [logLoad,  setLogLoad]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  function loadSummary() {
    setLoading(true);
    adminApi.systemSummary()
      .then(setSummary)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  function loadLogs(page = logPage) {
    setLogLoad(true);
    adminApi.auditLogs({ limit: 25, offset: page * 25 })
      .then(r => { setLogs(r.items); setLogTotal(r.total); })
      .catch(() => {})
      .finally(() => setLogLoad(false));
  }

  useEffect(() => { loadSummary(); }, []);
  useEffect(() => { loadLogs(logPage); }, [logPage]);

  const logCols: ColDef<AuditLogRow>[] = [
    { key: "ts",          label: "Time",   render: r => <span className="tabular-nums text-zinc-500">{fmtTs(r.ts)}</span> },
    { key: "admin_email", label: "Admin",  render: r => <span className="font-mono text-blue-400 text-[11px]">{r.admin_email ?? "—"}</span> },
    { key: "action",      label: "Action", render: r => <span className={`font-mono font-medium ${actionColor(r.action)}`}>{r.action}</span> },
    { key: "entity",      label: "Entity", render: r => <span className="text-zinc-500">{r.entity ?? "—"}</span> },
    {
      key: "metadata", label: "Details",
      render: r => r.metadata ? (
        <span className="text-zinc-600 text-[10px] font-mono truncate max-w-[160px] block">
          {JSON.stringify(r.metadata)}
        </span>
      ) : null,
    },
    { key: "ip_address", label: "IP", render: r => <span className="text-zinc-600 text-[10px]">{r.ip_address ?? "—"}</span> },
  ];

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-zinc-50">System</h1>
          <p className="text-sm text-zinc-500">Platform metrics and admin audit log</p>
        </div>
        <button onClick={loadSummary} className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 transition-colors">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {error && <div className="mb-3 text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">{error}</div>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard title="Total Users"    value={summary?.total_users ?? "—"}     icon={<Users size={16}/>}         color="blue"  loading={loading} />
        <StatCard title="Active (7d)"    value={summary?.active_users_7d ?? "—"} icon={<TrendingUp size={16}/>}    color="blue"  loading={loading} />
        <StatCard title="Requests Today" value={summary?.requests_today ?? "—"}  icon={<Activity size={16}/>}      color="zinc"  loading={loading} />
        <StatCard title="Requests (7d)"  value={summary?.requests_7d?.toLocaleString() ?? "—"} icon={<Server size={16}/>} color="zinc" loading={loading} />
        <StatCard title="Cache Hit Rate" value={summary ? `${summary.cache_hit_rate_pct}%` : "—"} icon={<Zap size={16}/>} color="green" loading={loading} sub="Today" />
        <StatCard title="Error Rate"     value={summary ? `${summary.error_rate_pct}%` : "—"}   icon={<AlertTriangle size={16}/>} color={summary && summary.error_rate_pct > 5 ? "red" : "zinc"} loading={loading} sub="5xx today" />
        <StatCard title="Avg Latency"    value={summary ? `${summary.avg_latency_ms}ms` : "—"}  icon={<Clock size={16}/>}         color="zinc"  loading={loading} sub="Today" />
        <StatCard title="Est. Cost Today" value={summary ? `$${summary.estimated_cost_today.toFixed(4)}` : "—"} icon={<DollarSign size={16}/>} color="amber" loading={loading} sub="FD calls" />
      </div>

      {/* Audit Log */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-zinc-400">Audit Log</h2>
          <span className="text-xs text-zinc-600">{logTotal} total entries</span>
        </div>
        <DataTable
          cols={logCols} rows={logs} keyField="id"
          total={logTotal} page={logPage} pageSize={25}
          onPage={p => setLogPage(p)} loading={logLoad}
          emptyMsg="No admin actions recorded yet."
        />
      </div>
    </div>
  );
}
