"use client";
import { ExternalLink } from "lucide-react";
import { NewsItem } from "@/lib/api";

export default function NewsSection({ news }: { news: NewsItem[] }) {
  if (!news.length) {
    return <div className="text-xs text-zinc-500 py-4">No news available</div>;
  }
  return (
    <div className="space-y-3">
      {news.map((item, i) => (
        <a
          key={i}
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-start justify-between gap-4 p-3 rounded-lg hover:bg-zinc-800/50 transition-colors group"
        >
          <div className="min-w-0">
            <div className="text-sm text-zinc-200 font-medium group-hover:text-blue-400 transition-colors line-clamp-2">
              {item.title}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs text-zinc-500">{item.source}</span>
              <span className="text-zinc-700">·</span>
              <span className="text-xs text-zinc-600">{item.date}</span>
            </div>
          </div>
          <ExternalLink size={13} className="text-zinc-600 group-hover:text-blue-400 shrink-0 mt-0.5 transition-colors" />
        </a>
      ))}
    </div>
  );
}
