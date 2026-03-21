"use client";

interface Tab {
  id: string;
  label: string;
  icon?: React.ReactNode;
}

interface Props {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (id: string) => void;
}

/**
 * PageHeader — per-page tab navigation, sits below GlobalHeader.
 * Sticky at top-16 (64px) so it locks in place under the fixed GlobalHeader.
 * Used by DashboardShell (Overview / Holdings / Risk / Simulator)
 * and any future page that needs tab navigation.
 */
export default function PageHeader({ tabs, activeTab, onTabChange }: Props) {
  return (
    <div className="border-b border-zinc-800 bg-zinc-900 sticky top-16 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 flex gap-1 overflow-x-auto scrollbar-thin">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => onTabChange(t.id)}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
              activeTab === t.id
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
