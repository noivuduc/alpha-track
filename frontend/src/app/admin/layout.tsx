"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import AdminSidebar from "@/components/admin/AdminSidebar";
import GlobalHeader from "@/components/GlobalHeader";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user)          { router.replace("/login");     return; }
    if (!user.is_admin) { router.replace("/dashboard"); return; }
  }, [user, loading, router]);

  if (loading || !user || !user.is_admin) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50 flex flex-col">
      <GlobalHeader />
      <div className="flex flex-1 pt-14">  {/* pt-14 = GlobalHeader height */}
        <AdminSidebar />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
