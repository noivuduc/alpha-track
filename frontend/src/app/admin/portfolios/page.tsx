"use client";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Search, Trash2 } from "lucide-react";
import { adminApi, AdminPortfolioRow } from "@/lib/api";
import DataTable, { ColDef } from "@/components/admin/DataTable";
import ConfirmModal from "@/components/admin/ConfirmModal";

const PAGE_SIZE = 20;

function fmtDate(d: string) {
  return new Date(d).toLocaleDateString();
}

export default function AdminPortfoliosPage() {
  const [rows,    setRows]    = useState<AdminPortfolioRow[]>([]);
  const [total,   setTotal]   = useState(0);
  const [page,    setPage]    = useState(0);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);
  const [userQ,   setUserQ]   = useState("");

  const [confirm, setConfirm] = useState<AdminPortfolioRow | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    adminApi.portfolios({ limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then(r => { setRows(r.items); setTotal(r.total); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [page]);

  useEffect(() => { load(); }, [load]);

  async function handleDelete() {
    if (!confirm) return;
    setDeleting(true);
    try {
      await adminApi.deletePortfolio(confirm.id);
      setConfirm(null);
      load();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setDeleting(false);
    }
  }

  const filtered = userQ
    ? rows.filter(r => r.user_email.toLowerCase().includes(userQ.toLowerCase()))
    : rows;

  const cols: ColDef<AdminPortfolioRow>[] = [
    {
      key: "user_email", label: "User",
      render: r => <span className="text-blue-400 font-mono text-[11px]">{r.user_email}</span>,
    },
    { key: "name",     label: "Portfolio",
      render: r => <span className="font-medium text-zinc-200">{r.name}</span> },
    { key: "currency", label: "Currency",
      render: r => <span className="text-zinc-500">{r.currency}</span> },
    { key: "position_count", label: "Positions",
      render: r => <span className="tabular-nums">{r.position_count}</span> },
    { key: "created_at", label: "Created", render: r => fmtDate(r.created_at) },
    { key: "updated_at", label: "Updated", render: r => fmtDate(r.updated_at) },
    {
      key: "actions", label: "",
      render: r => (
        <button
          onClick={e => { e.stopPropagation(); setConfirm(r); }}
          className="p-1.5 rounded hover:bg-zinc-700 text-zinc-600 hover:text-red-400 transition-colors"
          title="Delete portfolio"
        >
          <Trash2 size={13} />
        </button>
      ),
    },
  ];

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-zinc-50">Portfolios</h1>
          <p className="text-sm text-zinc-500">{total} total portfolios</p>
        </div>
        <button onClick={load} className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 transition-colors">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="flex items-center gap-2 mb-4">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
          <input value={userQ} onChange={e => setUserQ(e.target.value)}
            placeholder="Filter by user email…"
            className="pl-7 pr-3 py-1.5 text-xs rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 placeholder-zinc-600 outline-none focus:border-blue-500 w-56" />
        </div>
      </div>

      {error && <div className="mb-3 text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">{error}</div>}

      <DataTable
        cols={cols} rows={filtered} keyField="id"
        total={total} page={page} pageSize={PAGE_SIZE}
        onPage={setPage} loading={loading}
      />

      <ConfirmModal
        open={!!confirm}
        title="Delete Portfolio"
        message={`Delete "${confirm?.name}" owned by ${confirm?.user_email}? This cannot be undone — all positions and transactions will be lost.`}
        confirmLabel="Delete"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}
