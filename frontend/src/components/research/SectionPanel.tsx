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
      <div className="w-full flex items-center justify-between px-5 py-4">
        <button
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-3 flex-1 min-w-0 hover:opacity-80 transition-opacity text-left"
        >
          <span className="text-sm font-semibold text-zinc-200">{title}</span>
          <ChevronDown
            size={16}
            className={`text-zinc-500 transition-transform shrink-0 ${open ? "rotate-180" : ""}`}
          />
        </button>
        {action && <div className="ml-3 shrink-0">{action}</div>}
      </div>
      {open && <div className="px-5 pb-5">{children}</div>}
    </div>
  );
}
