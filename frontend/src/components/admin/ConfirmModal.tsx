"use client";
import { AlertTriangle } from "lucide-react";

interface Props {
  open:      boolean;
  title:     string;
  message:   string;
  confirmLabel?: string;
  danger?:   boolean;
  loading?:  boolean;
  onConfirm: () => void;
  onCancel:  () => void;
}

export default function ConfirmModal({
  open, title, message, confirmLabel = "Confirm",
  danger = true, loading = false, onConfirm, onCancel,
}: Props) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl p-6 w-full max-w-sm mx-4">
        <div className="flex items-start gap-3 mb-4">
          {danger && <AlertTriangle size={20} className="text-red-400 shrink-0 mt-0.5" />}
          <div>
            <h3 className="font-semibold text-zinc-50 text-sm">{title}</h3>
            <p className="text-xs text-zinc-400 mt-1">{message}</p>
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-3 py-1.5 text-xs rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors disabled:opacity-50 ${
              danger ? "bg-red-600 hover:bg-red-700 text-white" : "bg-blue-600 hover:bg-blue-700 text-white"
            }`}
          >
            {loading ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
