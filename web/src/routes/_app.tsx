import { useEffect } from "react";
import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { AppSidebar } from "@/components/layout/sidebar";
import { SidebarProvider } from "@/components/ui/sidebar";
import { CreateIncidentDialog } from "@/components/incidents/create-incident-dialog";
import { useAuthStore } from "@/stores/auth";
import { useCreateIncidentDialogStore } from "@/stores/create-incident-dialog";
import { client } from "@/lib/orpc";

export const Route = createFileRoute("/_app")({
  beforeLoad: async () => {
    const store = useAuthStore.getState();
    const token = store.token || store.hydrate();

    if (!token) {
      throw redirect({ to: "/login" });
    }

    if (!store.user) {
      try {
        const me = await client.auth.me();
        store.setUser(me);
      } catch {
        store.clearAuth();
        throw redirect({ to: "/login" });
      }
    }
  },
  component: AuthenticatedLayout,
});

function AuthenticatedLayout() {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        useCreateIncidentDialogStore.getState().setOpen(true);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <SidebarProvider>
      <AppSidebar />
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
      <CreateIncidentDialog />
    </SidebarProvider>
  );
}
