"use client";
import { useEffect, useState, useCallback } from "react";
import { Search, ShieldCheck, ShieldOff, KeyRound, RefreshCw, ChevronDown } from "lucide-react";
import { adminApi, AdminUserRow, AdminUserDetail, TierConfig } from "@/lib/api";
import DataTable, { ColDef } from "@/components/admin/DataTable";
import ConfirmModal from "@/components/admin/ConfirmModal";

const PAGE_SIZE = 20;

type Modal =
  | { type: "edit";           user: AdminUserDetail }
  | { type: "reset_password"; user: AdminUserRow; pw: string }
  | { type: "revoke_key";     user: AdminUserRow }
  | { type: "suspend";        user: AdminUserRow };

function TierBadge({ tier }: { tier: string }) {
  const c = { free: "text-zinc-400 bg-zinc-800", pro: "text-blue-400 bg-blue-900/30", fund: "text-amber-400 bg-amber-900/30" }[tier] ?? "text-zinc-400 bg-zinc-800";
  return <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${c}`}>{tier.toUpperCase()}</span>;
}

function StatusBadge({ active }: { active: boolean }) {
  return active
    ? <span className="text-[10px] font-medium text-emerald-400 bg-emerald-900/30 px-1.5 py-0.5 rounded">Active</span>
    : <span className="text-[10px] font-medium text-red-400 bg-red-900/30 px-1.5 py-0.5 rounded">Suspended</span>;
}

function fmtDate(d: string | null) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString();
}

export default function AdminUsersPage() {
  const [rows,    setRows]    = useState<AdminUserRow[]>([]);
  const [total,   setTotal]   = useState(0);
  const [page,    setPage]    = useState(0);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  // Filters
  const [emailQ,   setEmailQ]   = useState("");
  const [tierF,    setTierF]    = useState("");
  const [activeF,  setActiveF]  = useState<"" | "true" | "false">("");

  // Tiers for the edit form
  const [tiers, setTiers] = useState<TierConfig[]>([]);

  // Modals
  const [modal,     setModal]     = useState<Modal | null>(null);
  const [modalBusy, setModalBusy] = useState(false);
  const [modalErr,  setModalErr]  = useState<string | null>(null);

  // Edit-user form state
  const [editTier,     setEditTier]     = useState("");
  const [editIsActive, setEditIsActive] = useState(true);
  const [editIsAdmin,  setEditIsAdmin]  = useState(false);
  const [editName,     setEditName]     = useState("");
  const [resetPw,      setResetPw]      = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    adminApi.users({
      limit:     PAGE_SIZE,
      offset:    page * PAGE_SIZE,
      email:     emailQ || undefined,
      tier:      tierF  || undefined,
      is_active: activeF === "" ? undefined : activeF === "true",
    })
      .then(r => { setRows(r.items); setTotal(r.total); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [page, emailQ, tierF, activeF]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    adminApi.tiers().then(setTiers).catch(() => {});
  }, []);

  function openEdit(user: AdminUserRow) {
    setModalErr(null);
    adminApi.user(user.id).then(detail => {
      setEditTier(detail.tier);
      setEditIsActive(detail.is_active);
      setEditIsAdmin(detail.is_admin);
      setEditName(detail.full_name ?? "");
      setModal({ type: "edit", user: detail });
    }).catch(e => setError(e.message));
  }

  async function handleEditSave() {
    if (modal?.type !== "edit") return;
    setModalBusy(true); setModalErr(null);
    try {
      await adminApi.updateUser(modal.user.id, {
        tier: editTier, is_active: editIsActive, is_admin: editIsAdmin,
        full_name: editName || undefined,
      });
      setModal(null);
      load();
    } catch (e: unknown) {
      setModalErr((e as Error).message);
    } finally {
      setModalBusy(false);
    }
  }

  async function handleResetPw() {
    if (modal?.type !== "reset_password") return;
    setModalBusy(true); setModalErr(null);
    try {
      await adminApi.resetPassword(modal.user.id, resetPw);
      setModal(null); setResetPw("");
    } catch (e: unknown) {
      setModalErr((e as Error).message);
    } finally {
      setModalBusy(false);
    }
  }

  async function handleRevokeKey() {
    if (modal?.type !== "revoke_key") return;
    setModalBusy(true);
    try {
      await adminApi.revokeApiKey(modal.user.id);
      setModal(null); load();
    } catch (e: unknown) {
      setModalErr((e as Error).message);
    } finally {
      setModalBusy(false);
    }
  }

  async function handleSuspend() {
    if (modal?.type !== "suspend") return;
    setModalBusy(true);
    try {
      await adminApi.updateUser(modal.user.id, { is_active: !modal.user.is_active });
      setModal(null); load();
    } catch (e: unknown) {
      setModalErr((e as Error).message);
    } finally {
      setModalBusy(false);
    }
  }

  const cols: ColDef<AdminUserRow>[] = [
    {
      key: "email", label: "User",
      render: r => (
        <div>
          <div className="font-medium text-zinc-200">{r.email}</div>
          {r.full_name && <div className="text-zinc-500">{r.full_name}</div>}
        </div>
      ),
    },
    { key: "tier",   label: "Tier",   render: r => <TierBadge tier={r.tier} /> },
    { key: "status", label: "Status", render: r => <StatusBadge active={r.is_active} /> },
    { key: "portfolio_count", label: "Portfolios", render: r => <span className="tabular-nums">{r.portfolio_count}</span> },
    { key: "last_active_at",  label: "Last Active", render: r => fmtDate(r.last_active_at) },
    { key: "created_at",      label: "Joined",      render: r => fmtDate(r.created_at) },
    {
      key: "actions", label: "",
      render: r => (
        <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
          <button title={r.is_active ? "Suspend" : "Activate"}
            onClick={() => { setModalErr(null); setModal({ type: "suspend", user: r }); }}
            className="p-1.5 rounded hover:bg-zinc-700 text-zinc-500 hover:text-amber-400 transition-colors">
            {r.is_active ? <ShieldOff size={13} /> : <ShieldCheck size={13} />}
          </button>
          <button title="Reset password"
            onClick={() => { setResetPw(""); setModalErr(null); setModal({ type: "reset_password", user: r, pw: "" }); }}
            className="p-1.5 rounded hover:bg-zinc-700 text-zinc-500 hover:text-blue-400 transition-colors">
            <KeyRound size={13} />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="p-6 max-w-6xl">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-zinc-50">Users</h1>
          <p className="text-sm text-zinc-500">{total} total accounts</p>
        </div>
        <button onClick={load} className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 transition-colors">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
          <input value={emailQ} onChange={e => { setEmailQ(e.target.value); setPage(0); }}
            placeholder="Filter by email…"
            className="pl-7 pr-3 py-1.5 text-xs rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 placeholder-zinc-600 outline-none focus:border-blue-500 w-52" />
        </div>
        <div className="relative">
          <select value={tierF} onChange={e => { setTierF(e.target.value); setPage(0); }}
            className="pl-3 pr-7 py-1.5 text-xs rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 outline-none focus:border-blue-500 appearance-none">
            <option value="">All tiers</option>
            <option value="free">Free</option>
            <option value="pro">Pro</option>
            <option value="fund">Fund</option>
          </select>
          <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
        </div>
        <div className="relative">
          <select value={activeF} onChange={e => { setActiveF(e.target.value as "" | "true" | "false"); setPage(0); }}
            className="pl-3 pr-7 py-1.5 text-xs rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 outline-none focus:border-blue-500 appearance-none">
            <option value="">All statuses</option>
            <option value="true">Active</option>
            <option value="false">Suspended</option>
          </select>
          <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
        </div>
      </div>

      {error && <div className="mb-3 text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">{error}</div>}

      <DataTable
        cols={cols} rows={rows} keyField="id"
        total={total} page={page} pageSize={PAGE_SIZE}
        onPage={setPage} loading={loading}
        onRowClick={openEdit}
      />

      {/* Edit User Modal */}
      {modal?.type === "edit" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setModal(null)} />
          <div className="relative bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl p-6 w-full max-w-sm mx-4">
            <h3 className="font-semibold text-zinc-50 mb-4">Edit User</h3>
            <div className="text-xs text-zinc-400 mb-4 truncate">{modal.user.email}</div>

            <div className="space-y-3">
              <label className="block">
                <span className="text-xs text-zinc-500 mb-1 block">Tier</span>
                <div className="relative">
                  <select value={editTier} onChange={e => setEditTier(e.target.value)}
                    className="w-full pl-3 pr-7 py-1.5 text-xs rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 outline-none focus:border-blue-500 appearance-none">
                    {tiers.map(t => <option key={t.name} value={t.name}>{t.display_name} (${t.price_usd}/mo)</option>)}
                  </select>
                  <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
                </div>
              </label>

              <label className="block">
                <span className="text-xs text-zinc-500 mb-1 block">Full name</span>
                <input value={editName} onChange={e => setEditName(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 outline-none focus:border-blue-500" />
              </label>

              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-400">Account active</span>
                <button onClick={() => setEditIsActive(v => !v)}
                  className={`w-9 h-5 rounded-full transition-colors ${editIsActive ? "bg-blue-600" : "bg-zinc-700"}`}>
                  <span className={`block w-3.5 h-3.5 rounded-full bg-white shadow transition-transform mx-0.5 ${editIsActive ? "translate-x-4" : "translate-x-0"}`} />
                </button>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-400">Admin access</span>
                <button onClick={() => setEditIsAdmin(v => !v)}
                  className={`w-9 h-5 rounded-full transition-colors ${editIsAdmin ? "bg-amber-500" : "bg-zinc-700"}`}>
                  <span className={`block w-3.5 h-3.5 rounded-full bg-white shadow transition-transform mx-0.5 ${editIsAdmin ? "translate-x-4" : "translate-x-0"}`} />
                </button>
              </div>
            </div>

            {modalErr && <p className="text-xs text-red-400 mt-3">{modalErr}</p>}

            <div className="flex gap-2 justify-between mt-5">
              <button onClick={() => { setResetPw(""); setModalErr(null); setModal({ type: "reset_password", user: modal.user, pw: "" }); }}
                className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors px-2">
                Reset password
              </button>
              <div className="flex gap-2">
                <button onClick={() => setModal(null)} className="px-3 py-1.5 text-xs rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700">Cancel</button>
                <button onClick={handleEditSave} disabled={modalBusy} className="px-3 py-1.5 text-xs rounded-lg bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
                  {modalBusy ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Reset Password Modal */}
      {modal?.type === "reset_password" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setModal(null)} />
          <div className="relative bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl p-6 w-full max-w-sm mx-4">
            <h3 className="font-semibold text-zinc-50 mb-1">Reset Password</h3>
            <p className="text-xs text-zinc-500 mb-4">{modal.user.email}</p>
            <input type="password" value={resetPw} onChange={e => setResetPw(e.target.value)}
              placeholder="New password (min 8 chars, 1 uppercase, 1 digit)"
              className="w-full px-3 py-1.5 text-xs rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 outline-none focus:border-blue-500 mb-3" />
            {modalErr && <p className="text-xs text-red-400 mb-2">{modalErr}</p>}
            <div className="flex gap-2 justify-end">
              <button onClick={() => setModal(null)} className="px-3 py-1.5 text-xs rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700">Cancel</button>
              <button onClick={handleResetPw} disabled={modalBusy || resetPw.length < 8}
                className="px-3 py-1.5 text-xs rounded-lg bg-red-600 hover:bg-red-700 text-white disabled:opacity-50">
                {modalBusy ? "Resetting…" : "Reset"}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmModal
        open={modal?.type === "revoke_key"}
        title="Revoke API Key"
        message={`This will immediately invalidate the API key for ${(modal as { user?: AdminUserRow })?.user?.email}. They will need to generate a new one.`}
        confirmLabel="Revoke"
        loading={modalBusy}
        onConfirm={handleRevokeKey}
        onCancel={() => setModal(null)}
      />

      <ConfirmModal
        open={modal?.type === "suspend"}
        title={(modal as { user?: AdminUserRow })?.user?.is_active ? "Suspend Account" : "Activate Account"}
        message={(modal as { user?: AdminUserRow })?.user?.is_active
          ? `Suspend ${(modal as { user?: AdminUserRow })?.user?.email}? They won't be able to log in.`
          : `Reactivate ${(modal as { user?: AdminUserRow })?.user?.email}?`}
        confirmLabel={(modal as { user?: AdminUserRow })?.user?.is_active ? "Suspend" : "Activate"}
        danger={(modal as { user?: AdminUserRow })?.user?.is_active}
        loading={modalBusy}
        onConfirm={handleSuspend}
        onCancel={() => setModal(null)}
      />
    </div>
  );
}
