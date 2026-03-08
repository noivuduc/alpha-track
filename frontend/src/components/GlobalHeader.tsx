"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, BarChart2 } from "lucide-react";
import SearchAutocomplete from "@/components/research/SearchAutocomplete";

interface Props {
  showBack?: boolean;
}

export default function GlobalHeader({ showBack = false }: Props) {
  const router = useRouter();
  return (
    <header className="fixed top-0 left-0 right-0 h-12 bg-zinc-950/95 backdrop-blur-sm border-b border-zinc-800 z-50 flex items-center gap-3 px-4">
      {/* Logo / back */}
      <div className="flex items-center gap-2 shrink-0">
        {showBack ? (
          <button
            onClick={() => router.push("/dashboard")}
            className="flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200 transition-colors text-sm"
          >
            <ArrowLeft size={15} />
            <span className="hidden sm:inline text-sm">Dashboard</span>
          </button>
        ) : (
          <Link href="/dashboard" className="flex items-center gap-2 text-zinc-200 hover:text-white transition-colors">
            <BarChart2 size={18} className="text-blue-400" />
            <span className="font-semibold text-sm hidden sm:inline">AlphaDesk</span>
          </Link>
        )}
      </div>

      <div className="w-px h-4 bg-zinc-800 shrink-0" />

      {/* Search */}
      <div className="flex-1 max-w-sm">
        <SearchAutocomplete placeholder="Search company or ticker…" />
      </div>
    </header>
  );
}
