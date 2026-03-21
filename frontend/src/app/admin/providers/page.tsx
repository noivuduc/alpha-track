"use client";
import { useEffect, useState } from "react";
import { RefreshCw, ChevronUp, ChevronDown, Save } from "lucide-react";
import { adminApi, DataProviderConfig, TierConfig } from "@/lib/api";

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!on)}
      className={`w-9 h-5 rounded-full transition-colors ${on ? "bg-blue-600" : "bg-zinc-700"}`}>
      <span className={`block w-3.5 h-3.5 rounded-full bg-white shadow transition-transform mx-0.5 ${on ? "translate-x-4" : "translate-x-0"}`} />
    </button>
  );
}

export default function AdminProvidersPage() {
  const [providers, setProviders] = useState<DataProviderConfig[]>([]);
  const [tiers,     setTiers]     = useState<TierConfig[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [saving,    setSaving]    = useState<string | null>(null);
  const [error,     setError]     = useState<string | null>(null);
  const [success,   setSuccess]   = useState<string | null>(null);

  // Edit state per provider
  const [edits, setEdits] = useState<Record<string, Partial<DataProviderConfig>>>({});

  function load() {
    setLoading(true);
    Promise.all([adminApi.providers(), adminApi.tiers()])
      .then(([p, t]) => { setProviders(p); setTiers(t); setEdits({}); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  function getEdit(name: string): DataProviderConfig {
    const base = providers.find(p => p.name === name)!;
    return { ...base, ...edits[name] };
  }

  function setField(name: string, field: keyof DataProviderConfig, val: unknown) {
    setEdits(prev => ({ ...prev, [name]: { ...prev[name], [field]: val } }));
  }

  async function save(name: string) {
    const patch = edits[name];
    if (!patch || !Object.keys(patch).length) return;
    setSaving(name); setError(null); setSuccess(null);
    try {
      const updated = await adminApi.updateProvider(name, patch);
      setProviders(prev => prev.map(p => p.name === name ? updated : p));
      setEdits(prev => { const n = { ...prev }; delete n[name]; return n; });
      setSuccess(`${name} saved.`);
      setTimeout(() => setSuccess(null), 3000);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSaving(null);
    }
  }

  async function move(name: string, dir: -1 | 1) {
    const sorted = [...providers].sort((a, b) => a.priority - b.priority);
    const idx    = sorted.findIndex(p => p.name === name);
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= sorted.length) return;
    [sorted[idx], sorted[newIdx]] = [sorted[newIdx], sorted[idx]];
    const order = sorted.map(p => p.name);
    try {
      await adminApi.reorderProviders(order);
      load();
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  }

  const sorted = [...providers].sort((a, b) => a.priority - b.priority);

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-zinc-50">Data Providers</h1>
          <p className="text-sm text-zinc-500">Manage external data sources</p>
        </div>
        <button onClick={load} className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 transition-colors">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {error   && <div className="mb-3 text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">{error}</div>}
      {success && <div className="mb-3 text-xs text-emerald-400 bg-emerald-900/20 border border-emerald-800 rounded-lg px-3 py-2">{success}</div>}

      {loading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="h-28 rounded-xl bg-zinc-800 animate-pulse" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {sorted.map((p, idx) => {
            const e = getEdit(p.name);
            const dirty = !!edits[p.name] && Object.keys(edits[p.name]).length > 0;
            return (
              <div key={p.name} className={`rounded-xl border p-4 transition-colors ${e.enabled ? "border-zinc-700 bg-zinc-900" : "border-zinc-800 bg-zinc-900/50 opacity-60"}`}>
                <div className="flex items-start justify-between gap-4">
                  {/* Left: name + toggle */}
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex flex-col gap-0.5">
                      <button onClick={() => move(p.name, -1)} disabled={idx === 0}
                        className="p-0.5 rounded hover:bg-zinc-700 disabled:opacity-20 text-zinc-500"><ChevronUp size={12}/></button>
                      <button onClick={() => move(p.name, 1)} disabled={idx === sorted.length - 1}
                        className="p-0.5 rounded hover:bg-zinc-700 disabled:opacity-20 text-zinc-500"><ChevronDown size={12}/></button>
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold text-zinc-200">{p.display_name}</span>
                        <span className="text-[10px] text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">priority {e.priority}</span>
                      </div>
                      {p.notes && <p className="text-xs text-zinc-500 mt-0.5">{p.notes}</p>}
                    </div>
                  </div>
                  <Toggle on={e.enabled} onChange={v => setField(p.name, "enabled", v)} />
                </div>

                {/* Editable fields */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-4">
                  <label className="block">
                    <span className="text-[10px] text-zinc-500 block mb-1">Rate limit (RPM)</span>
                    <input type="number" value={e.rate_limit_rpm} min={1}
                      onChange={ev => setField(p.name, "rate_limit_rpm", Number(ev.target.value))}
                      className="w-full px-2 py-1 text-xs rounded bg-zinc-800 border border-zinc-700 text-zinc-300 outline-none focus:border-blue-500" />
                  </label>
                  <label className="block">
                    <span className="text-[10px] text-zinc-500 block mb-1">Cost per call ($)</span>
                    <input type="number" value={e.cost_per_call_usd} min={0} step={0.0001}
                      onChange={ev => setField(p.name, "cost_per_call_usd", Number(ev.target.value))}
                      className="w-full px-2 py-1 text-xs rounded bg-zinc-800 border border-zinc-700 text-zinc-300 outline-none focus:border-blue-500" />
                  </label>
                  <label className="block">
                    <span className="text-[10px] text-zinc-500 block mb-1">Notes</span>
                    <input value={e.notes ?? ""} onChange={ev => setField(p.name, "notes", ev.target.value)}
                      className="w-full px-2 py-1 text-xs rounded bg-zinc-800 border border-zinc-700 text-zinc-300 outline-none focus:border-blue-500" />
                  </label>
                </div>

                {dirty && (
                  <div className="flex justify-end mt-3">
                    <button onClick={() => save(p.name)} disabled={saving === p.name}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 transition-colors">
                      <Save size={12} />
                      {saving === p.name ? "Saving…" : "Save changes"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Tier limits table */}
      {tiers.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3">Subscription Tier Limits</h2>
          <div className="overflow-x-auto rounded-xl border border-zinc-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/60">
                  {["Tier", "Price", "Portfolios", "Positions", "RPM", "RPD", "AI/day"].map(h => (
                    <th key={h} className="text-left py-2 px-3 font-medium text-zinc-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tiers.map(t => (
                  <tr key={t.name} className="border-b border-zinc-800/50">
                    <td className="py-2 px-3 font-medium text-zinc-200">{t.display_name}</td>
                    <td className="py-2 px-3 text-zinc-400">${t.price_usd}/mo</td>
                    <td className="py-2 px-3 tabular-nums">{t.max_portfolios >= 999 ? "∞" : t.max_portfolios}</td>
                    <td className="py-2 px-3 tabular-nums">{t.max_positions >= 999 ? "∞" : t.max_positions}</td>
                    <td className="py-2 px-3 tabular-nums">{t.rpm}</td>
                    <td className="py-2 px-3 tabular-nums">{t.rpd.toLocaleString()}</td>
                    <td className="py-2 px-3 tabular-nums">{t.ai_per_day >= 999 ? "∞" : t.ai_per_day}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-zinc-600 mt-2">Note: runtime rate limits use in-memory config. Restart the backend after changing tier limits to apply.</p>
        </div>
      )}
    </div>
  );
}
