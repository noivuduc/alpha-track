"use client";
import { ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

export interface ColDef<T> {
  key:      string;
  label:    string;
  render?:  (row: T) => ReactNode;
  className?: string;
}

interface Props<T> {
  cols:        ColDef<T>[];
  rows:        T[];
  keyField:    keyof T;
  total:       number;
  page:        number;      // 0-based
  pageSize:    number;
  onPage:      (page: number) => void;
  loading?:    boolean;
  onRowClick?: (row: T) => void;
  emptyMsg?:   string;
}

export default function DataTable<T>({
  cols, rows, keyField, total, page, pageSize, onPage,
  loading = false, onRowClick, emptyMsg = "No records found.",
}: Props<T>) {
  const pages    = Math.ceil(total / pageSize);
  const fromRow  = total === 0 ? 0 : page * pageSize + 1;
  const toRow    = Math.min((page + 1) * pageSize, total);

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto rounded-xl border border-zinc-800">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/60">
              {cols.map(c => (
                <th key={c.key} className={`text-left py-2.5 px-3 font-medium text-zinc-500 whitespace-nowrap ${c.className ?? ""}`}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-zinc-800/50">
                  {cols.map(c => (
                    <td key={c.key} className="py-2.5 px-3">
                      <div className="h-4 bg-zinc-800 rounded animate-pulse w-3/4" />
                    </td>
                  ))}
                </tr>
              ))
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={cols.length} className="py-10 px-3 text-center text-zinc-500">
                  {emptyMsg}
                </td>
              </tr>
            ) : (
              rows.map(row => (
                <tr
                  key={String(row[keyField])}
                  onClick={() => onRowClick?.(row)}
                  className={`border-b border-zinc-800/50 transition-colors ${
                    onRowClick ? "cursor-pointer hover:bg-zinc-800/40" : ""
                  }`}
                >
                  {cols.map(c => (
                    <td key={c.key} className={`py-2.5 px-3 text-zinc-300 ${c.className ?? ""}`}>
                      {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > 0 && (
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>{fromRow}–{toRow} of {total}</span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPage(page - 1)}
              disabled={page === 0 || loading}
              className="p-1 rounded hover:bg-zinc-800 disabled:opacity-30 transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
            <span className="px-2 tabular-nums">{page + 1} / {pages}</span>
            <button
              onClick={() => onPage(page + 1)}
              disabled={page >= pages - 1 || loading}
              className="p-1 rounded hover:bg-zinc-800 disabled:opacity-30 transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
