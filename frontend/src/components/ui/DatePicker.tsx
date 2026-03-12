"use client";
import { useState, useRef, useEffect } from "react";
import { ChevronLeft, ChevronRight, Calendar } from "lucide-react";

interface Props {
  value:    string;           // YYYY-MM-DD
  onChange: (v: string) => void;
  max?:     string;           // YYYY-MM-DD — default: today
  className?: string;
}

const MONTHS = ["January","February","March","April","May","June",
                 "July","August","September","October","November","December"];
const DOW    = ["Su","Mo","Tu","We","Th","Fr","Sa"];

function parseDate(s: string): Date | null {
  if (!s || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function toStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function formatDisplay(s: string): string {
  const d = parseDate(s);
  if (!d) return "Select date";
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export default function DatePicker({ value, onChange, max, className = "" }: Props) {
  const [open, setOpen]       = useState(false);
  const ref                   = useRef<HTMLDivElement>(null);

  // Calendar view state — initialise from value or today
  const initDate = parseDate(value) ?? new Date();
  const [viewYear,  setViewYear]  = useState(initDate.getFullYear());
  const [viewMonth, setViewMonth] = useState(initDate.getMonth());

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Sync view when value changes externally
  useEffect(() => {
    const d = parseDate(value);
    if (d) { setViewYear(d.getFullYear()); setViewMonth(d.getMonth()); }
  }, [value]);

  const maxDate = parseDate(max ?? toStr(new Date()));

  const prevMonth = () => {
    if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11); }
    else setViewMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0); }
    else setViewMonth(m => m + 1);
  };

  // Build calendar grid
  const firstDay = new Date(viewYear, viewMonth, 1).getDay();  // 0=Sun
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(firstDay).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  // Pad to full weeks
  while (cells.length % 7 !== 0) cells.push(null);

  const selectedDate = parseDate(value);

  const selectDay = (day: number) => {
    const d = new Date(viewYear, viewMonth, day);
    if (maxDate && d > maxDate) return;
    onChange(toStr(d));
    setOpen(false);
  };

  const isSelected = (day: number) =>
    selectedDate?.getFullYear() === viewYear &&
    selectedDate?.getMonth()    === viewMonth &&
    selectedDate?.getDate()     === day;

  const isDisabled = (day: number) => {
    if (!maxDate) return false;
    return new Date(viewYear, viewMonth, day) > maxDate;
  };

  const isToday = (day: number) => {
    const t = new Date();
    return t.getFullYear() === viewYear && t.getMonth() === viewMonth && t.getDate() === day;
  };

  return (
    <div ref={ref} className={`relative ${className}`}>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 hover:border-zinc-500 focus:outline-none focus:border-blue-500 transition-colors whitespace-nowrap"
      >
        <Calendar size={13} className="text-zinc-500 shrink-0" />
        {formatDisplay(value)}
      </button>

      {/* Calendar popover */}
      {open && (
        <div className="absolute z-50 mt-1 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl p-3 w-64"
             style={{ top: "100%", left: 0 }}>

          {/* Month navigation */}
          <div className="flex items-center justify-between mb-3">
            <button type="button" onClick={prevMonth}
              className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors">
              <ChevronLeft size={15} />
            </button>
            <span className="text-sm font-semibold text-zinc-200">
              {MONTHS[viewMonth]} {viewYear}
            </span>
            <button type="button" onClick={nextMonth}
              className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors">
              <ChevronRight size={15} />
            </button>
          </div>

          {/* Day-of-week headers */}
          <div className="grid grid-cols-7 mb-1">
            {DOW.map(d => (
              <div key={d} className="text-center text-[10px] font-semibold text-zinc-600 py-1">{d}</div>
            ))}
          </div>

          {/* Day grid */}
          <div className="grid grid-cols-7 gap-y-0.5">
            {cells.map((day, i) => {
              if (!day) return <div key={i} />;
              const sel  = isSelected(day);
              const dis  = isDisabled(day);
              const tod  = isToday(day);
              return (
                <button
                  key={i}
                  type="button"
                  disabled={dis}
                  onClick={() => selectDay(day)}
                  className={`
                    h-8 w-8 mx-auto rounded-lg text-xs font-medium transition-colors
                    ${sel  ? "bg-blue-600 text-white"
                    : tod  ? "text-blue-400 hover:bg-zinc-800"
                    : dis  ? "text-zinc-700 cursor-not-allowed"
                    :        "text-zinc-300 hover:bg-zinc-800"}
                  `}
                >
                  {day}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
