"use client";
import { useEffect, useState } from "react";
import { Users, DollarSign, Activity, Database, TrendingUp, Zap } from "lucide-react";
import { adminApi, SystemSummary } from "@/lib/api";
import StatCard from "@/components/admin/StatCard";
import Link from "next/link";

export default function AdminOverviewPage() {
  const [summary, setSummary] = useState<SystemSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    adminApi.systemSummary()
      .then(setSummary)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 max-w-5xl">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-zinc-50">Admin Overview</h1>
        <p className="text-sm text-zinc-500 mt-1">Platform health at a glance</p>
      </div>

      {error && (
        <div className="mb-4 bg-red-900/30 border border-red-700 text-red-300 text-xs rounded-lg px-4 py-2">{error}</div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8">
        <StatCard title="Total Users"    value={summary?.total_users ?? "—"}     icon={<Users size={16}/>}      color="blue"  loading={loading} sub={`${summary?.active_users_7d ?? "—"} active 7d`} />
        <StatCard title="Requests Today" value={summary?.requests_today ?? "—"}  icon={<Activity size={16}/>}   color="zinc"  loading={loading} sub={`${summary?.requests_7d ?? "—"} last 7d`} />
        <StatCard title="Cache Hit Rate" value={summary ? `${summary.cache_hit_rate_pct}%` : "—"} icon={<Zap size={16}/>} color="green" loading={loading} sub="Today" />
        <StatCard title="Error Rate"     value={summary ? `${summary.error_rate_pct}%` : "—"}     icon={<TrendingUp size={16}/>} color={summary && summary.error_rate_pct > 5 ? "red" : "zinc"} loading={loading} sub="5xx today" />
        <StatCard title="Paid API Calls" value={summary?.paid_calls_today ?? "—"} icon={<Database size={16}/>}  color="amber" loading={loading} sub="FD calls today" />
        <StatCard title="Est. Cost Today" value={summary ? `$${summary.estimated_cost_today.toFixed(4)}` : "—"} icon={<DollarSign size={16}/>} color="amber" loading={loading} sub="FD cost estimate" />
        <StatCard title="Avg Latency"    value={summary ? `${summary.avg_latency_ms}ms` : "—"}     icon={<Activity size={16}/>}  color="zinc"  loading={loading} sub="Today" />
        <StatCard title="Active 30d"     value={summary?.active_users_30d ?? "—"} icon={<Users size={16}/>}     color="blue"  loading={loading} sub="Unique users" />
      </div>

      {/* Quick links */}
      <div>
        <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">Quick Actions</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { href: "/admin/users",      label: "Manage Users",      desc: "View, edit, suspend accounts" },
            { href: "/admin/providers",  label: "Data Providers",    desc: "Toggle and configure providers" },
            { href: "/admin/portfolios", label: "All Portfolios",    desc: "Inspect and delete portfolios" },
            { href: "/admin/costs",      label: "Cost Tracking",     desc: "API usage and cost breakdown" },
            { href: "/admin/system",     label: "System & Audit",    desc: "Audit log and metrics" },
          ].map(({ href, label, desc }) => (
            <Link key={href} href={href}
              className="block p-4 rounded-xl border border-zinc-800 bg-zinc-900 hover:border-zinc-600 hover:bg-zinc-800/60 transition-colors">
              <div className="font-medium text-sm text-zinc-200">{label}</div>
              <div className="text-xs text-zinc-500 mt-0.5">{desc}</div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
