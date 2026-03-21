"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Users, Database, Briefcase,
  DollarSign, Activity, ChevronRight,
} from "lucide-react";

const NAV = [
  { href: "/admin",            label: "Overview",   icon: LayoutDashboard },
  { href: "/admin/users",      label: "Users",      icon: Users           },
  { href: "/admin/providers",  label: "Providers",  icon: Database        },
  { href: "/admin/portfolios", label: "Portfolios", icon: Briefcase       },
  { href: "/admin/costs",      label: "Costs",      icon: DollarSign      },
  { href: "/admin/system",     label: "System",     icon: Activity        },
];

export default function AdminSidebar() {
  const path = usePathname();

  return (
    <aside className="w-52 shrink-0 bg-zinc-900 border-r border-zinc-800 flex flex-col">
      <div className="px-4 py-4 border-b border-zinc-800">
        <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Admin</span>
      </div>
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/admin" ? path === "/admin" : path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors group ${
                active
                  ? "bg-blue-600/15 text-blue-400 font-medium"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
              }`}
            >
              <Icon size={15} />
              <span className="flex-1">{label}</span>
              {active && <ChevronRight size={12} className="text-blue-500" />}
            </Link>
          );
        })}
      </nav>
      <div className="px-4 py-3 border-t border-zinc-800">
        <span className="text-[10px] text-zinc-600">Internal tool — admins only</span>
      </div>
    </aside>
  );
}
