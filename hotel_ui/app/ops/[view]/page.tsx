"use client";
import { useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { useOpsStore } from "@/store/opsStore";
import { getOpsGuests, getRoles } from "@/lib/api";
import HotelHeader from "@/components/shared/HotelHeader";
import ResizableLayout from "@/components/shared/ResizableLayout";
import OpsSidebar from "@/components/ops/OpsSidebar";
import DashboardView from "@/components/ops/DashboardView";
import LogCallView from "@/components/ops/LogCallView";
import BriefingsView from "@/components/ops/BriefingsView";
import AllergyView from "@/components/ops/AllergyView";
import GroupBriefView from "@/components/ops/GroupBriefView";
import DigestView from "@/components/ops/DigestView";
import RoleMemoryView from "@/components/ops/RoleMemoryView";
import HowItWorksView from "@/components/ops/HowItWorksView";

const VIEW_COMPONENTS: Record<string, React.ComponentType> = {
  dashboard: DashboardView,
  "log-call": LogCallView,
  "pre-arrival": BriefingsView,
  allergy: AllergyView,
  "group-brief": GroupBriefView,
  digest: DigestView,
  "role-memory": RoleMemoryView,
  "how-it-works": HowItWorksView,
};

export default function OpsViewPage() {
  const params = useParams();
  const router = useRouter();
  const store = useOpsStore();
  const { authenticated, activeRole, guestsLoaded } = store;

  const view = Array.isArray(params.view) ? params.view[0] : (params.view ?? "dashboard");

  // Guard: redirect to login if not authenticated
  useEffect(() => {
    if (!authenticated) router.push("/ops");
  }, [authenticated]);

  // Sync active view with URL
  useEffect(() => {
    if (view && store.activeView !== view) store.setActiveView(view);
  }, [view]);

  // Load guests once
  useEffect(() => {
    if (!guestsLoaded && authenticated) {
      getOpsGuests().then((r) => store.setGuests(r.guests)).catch(() => {});
    }
  }, [authenticated, guestsLoaded]);

  // Load roles once so sidebar shows live count
  useEffect(() => {
    if (authenticated && Object.keys(store.roles).length === 0) {
      getRoles().then((r) => store.setRoles(r.roles)).catch(() => {});
    }
  }, [authenticated]);

  // Guard: check view is allowed for this role
  useEffect(() => {
    if (activeRole && view && !activeRole.allowed_views.includes(view)) {
      router.push(`/ops/${activeRole.default_view}`);
    }
  }, [activeRole, view]);

  if (!authenticated || !activeRole) return null;

  const ViewComponent = VIEW_COMPONENTS[view];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
      <HotelHeader portalLabel="Operations Portal" />

      <ResizableLayout
        sidebar={<OpsSidebar />}
        main={
          ViewComponent ? <ViewComponent /> : (
            <div style={{ padding: "2rem", color: "rgba(26,26,26,0.5)" }}>
              View &ldquo;{view}&rdquo; not found or not accessible for your role.
            </div>
          )
        }
      />
    </div>
  );
}
