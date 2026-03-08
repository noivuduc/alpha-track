"use client";
import { useState } from "react";
import { ChevronDown } from "lucide-react";

interface Props {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  action?: React.ReactNode;
}

export default function SectionPanel({ title, defaultOpen = true, children, action }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-zinc-800/50 transition-colors"
      >
        <span className="text-sm font-semibold text-zinc-200">{title}</span>
        <div className="flex items-center gap-3">
          {action && <div onClick={e => e.stopPropagation()}>{action}</div>}
          <ChevronDown
            size={16}
            className={`text-zinc-500 transition-transform ${open ? "rotate-180" : ""}`}
          />
        </div>
      </button>
      {open && <div className="px-5 pb-5">{children}</div>}
    </div>
  );
}
