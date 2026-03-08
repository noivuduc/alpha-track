"use client";
import { useState } from "react";
import { ChevronDown } from "lucide-react";

interface Props {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  action?: React.ReactNode;
  id?: string;
}

export default function SectionPanel({ title, defaultOpen = true, children, action, id }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div id={id} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden scroll-mt-28">
      <div className="w-full flex items-center justify-between px-5 py-3.5 border-b border-zinc-800/60">
        <button
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-2.5 flex-1 min-w-0 hover:opacity-80 transition-opacity text-left"
        >
          <span className="text-sm font-semibold text-zinc-200 tracking-tight">{title}</span>
          <ChevronDown
            size={15}
            className={`text-zinc-600 transition-transform shrink-0 ${open ? "rotate-180" : ""}`}
          />
        </button>
        {action && <div className="ml-3 shrink-0">{action}</div>}
      </div>
      {open && <div className="p-5">{children}</div>}
    </div>
  );
}
