import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: Dashboard,
});

function Dashboard() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center">
        <h1 className="text-3xl font-bold">Chronos</h1>
        <p className="mt-2 text-muted-foreground">Ops AI Agent</p>
      </div>
    </div>
  );
}
