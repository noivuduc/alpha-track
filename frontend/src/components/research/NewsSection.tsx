"use client";
import { ExternalLink } from "lucide-react";
import { NewsItem } from "@/lib/api";

function fmtDate(d: string): string {
  if (!d) return "";
  try {
    return new Date(d).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return d;
  }
}

export default function NewsSection({ news }: { news: NewsItem[] }) {
  if (!news.length) {
    return <div className="text-xs text-zinc-500 py-4">No news available</div>;
  }
  return (
    <div className="divide-y divide-zinc-800/60">
      {news.map((item, i) => (
        <a
          key={i}
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-start justify-between gap-4 py-3.5 px-1 first:pt-1 last:pb-1 hover:bg-zinc-800/40 -mx-1 px-2 rounded-lg transition-colors group"
        >
          <div className="min-w-0 flex-1">
            {/* Title */}
            <div className="text-sm font-medium text-zinc-100 group-hover:text-white transition-colors line-clamp-2 leading-snug">
              {(item as NewsItem & { headline?: string }).headline || item.title || "Untitled article"}
            </div>
            {/* Meta */}
            <div className="flex items-center gap-1.5 mt-1.5">
              {item.source && (
                <span className="text-xs text-zinc-500 font-medium">{item.source}</span>
              )}
              {item.source && item.date && (
                <span className="text-zinc-700">·</span>
              )}
              {item.date && (
                <span className="text-xs text-zinc-600">{fmtDate(item.date)}</span>
              )}
            </div>
          </div>
          <ExternalLink
            size={13}
            className="text-zinc-600 group-hover:text-blue-400 shrink-0 mt-0.5 transition-colors"
          />
        </a>
      ))}
    </div>
  );
}
