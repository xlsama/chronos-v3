import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/infrastructure/")({
  component: InfrastructurePage,
});

function InfrastructurePage() {
  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold">Infrastructure</h1>
      <p className="mt-2 text-muted-foreground">
        Infrastructure management will be available in Phase 2.
      </p>
    </div>
  );
}
