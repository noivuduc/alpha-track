"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, X } from "lucide-react";
import { searchApi, SearchResult } from "@/lib/api";
import TickerLogo from "@/components/ui/TickerLogo";

// Highlight matching text
function Highlight({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-blue-500/30 text-blue-300 rounded px-0.5">{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  );
}


export default function SearchAutocomplete({ placeholder = "Search ticker or company…" }: { placeholder?: string }) {
  const router = useRouter();
  const [query,    setQuery]    = useState("");
  const [results,  setResults]  = useState<SearchResult[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [active,   setActive]   = useState(-1);
  const [open,     setOpen]     = useState(false);
  const inputRef  = useRef<HTMLInputElement>(null);
  const listRef   = useRef<HTMLUListElement>(null);
  const debounce  = useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); setOpen(false); return; }
    setLoading(true);
    try {
      const res = await searchApi.search(q);
      setResults(res);
      setOpen(res.length > 0);
      setActive(-1);
    } catch { setResults([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    if (query.length < 1) { setResults([]); setOpen(false); return; }
    debounce.current = setTimeout(() => search(query), 300);
    return () => { if (debounce.current) clearTimeout(debounce.current); };
  }, [query, search]);

  function navigate(sym: string) {
    setQuery("");
    setResults([]);
    setOpen(false);
    router.push(`/research/${sym.toUpperCase()}`);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive(a => Math.min(a + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive(a => Math.max(a - 1, -1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (active >= 0 && results[active]) navigate(results[active].symbol);
      else if (query.trim().length >= 1) navigate(query.trim().toUpperCase());
    } else if (e.key === "Escape") {
      setOpen(false);
      setActive(-1);
    }
  }

  // Scroll active item into view
  useEffect(() => {
    if (active >= 0 && listRef.current) {
      const el = listRef.current.children[active] as HTMLElement;
      el?.scrollIntoView({ block: "nearest" });
    }
  }, [active]);

  return (
    <div className="relative w-full max-w-md">
      <div className="relative flex items-center">
        <Search size={14} className="absolute left-3 text-zinc-500 pointer-events-none" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => results.length > 0 && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder={placeholder}
          className="w-full bg-zinc-800 border border-zinc-700 text-zinc-200 placeholder-zinc-500 text-sm rounded-lg pl-8 pr-8 py-2 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-colors"
        />
        {query && (
          <button onClick={() => { setQuery(""); setResults([]); setOpen(false); inputRef.current?.focus(); }}
            className="absolute right-2.5 text-zinc-600 hover:text-zinc-400 transition-colors">
            <X size={13} />
          </button>
        )}
        {loading && (
          <div className="absolute right-8 w-3.5 h-3.5 border border-blue-500 border-t-transparent rounded-full animate-spin" />
        )}
      </div>

      {open && results.length > 0 && (
        <ul
          ref={listRef}
          className="absolute left-0 right-0 mt-1.5 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl z-50 max-h-72 overflow-y-auto scrollbar-thin"
        >
          {results.map((r, i) => (
            <li key={r.symbol}>
              <button
                onMouseDown={() => navigate(r.symbol)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors ${
                  i === active ? "bg-zinc-700/70" : "hover:bg-zinc-800"
                } ${i < results.length - 1 ? "border-b border-zinc-800" : ""}`}
              >
                {/* Logo */}
                <TickerLogo ticker={r.symbol} size={32} rounded="md" />
                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-semibold text-sm text-zinc-100">
                      <Highlight text={r.symbol} query={query} />
                    </span>
                    {r.exchange && <span className="text-xs text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">{r.exchange}</span>}
                    {r.type && r.type !== "equity" && <span className="text-xs text-amber-500">{r.type.toUpperCase()}</span>}
                  </div>
                  <div className="text-xs text-zinc-400 truncate">
                    <Highlight text={r.name} query={query} />
                  </div>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
