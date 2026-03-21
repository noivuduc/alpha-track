"use client";
import { useState, useEffect } from "react";

export interface NavSection { id: string; label: string; }

interface Props {
  sections:    NavSection[];
  horizontal?: boolean;
  variant?:    "pills" | "tabs";
}

export default function ResearchNav({ sections, horizontal = false, variant = "pills" }: Props) {
  const [active, setActive] = useState<string>("");

  useEffect(() => {
    const visibilityMap: Record<string, number> = {};
    const observers: IntersectionObserver[] = [];

    sections.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (!el) return;
      const obs = new IntersectionObserver(
        ([entry]) => {
          visibilityMap[id] = entry.intersectionRatio;
          const topId = Object.entries(visibilityMap).sort((a, b) => b[1] - a[1])[0]?.[0];
          if (topId) setActive(topId);
        },
        { threshold: [0, 0.1, 0.25, 0.5, 0.75, 1.0], rootMargin: "-48px 0px -30% 0px" }
      );
      obs.observe(el);
      observers.push(obs);
    });

    return () => observers.forEach(o => o.disconnect());
  }, [sections]);

  function scrollTo(id: string) {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (horizontal && variant === "tabs") {
    return (
      <nav className="flex items-center overflow-x-auto scrollbar-thin">
        {sections.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => scrollTo(id)}
            className={`px-4 py-3 text-sm font-medium whitespace-nowrap shrink-0 border-b-2 transition-colors ${
              active === id
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>
    );
  }

  if (horizontal) {
    return (
      <nav className="flex items-center gap-0.5 overflow-x-auto scrollbar-none">
        {sections.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => scrollTo(id)}
            className={`px-3 py-1.5 rounded-lg text-xs whitespace-nowrap shrink-0 transition-colors ${
              active === id
                ? "bg-blue-600/20 text-blue-400 font-medium"
                : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>
    );
  }

  return (
    <nav className="bg-zinc-900 border border-zinc-800 rounded-xl p-2">
      <div className="text-[10px] font-semibold text-zinc-500 px-2 py-1.5 uppercase tracking-wider">
        Sections
      </div>
      {sections.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => scrollTo(id)}
          className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition-colors ${
            active === id
              ? "bg-blue-600/20 text-blue-400 font-medium"
              : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
          }`}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
