import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { AlertCircle } from "lucide-react";
import dayjs from "@/lib/dayjs";
import { getIncidents } from "@/api/incidents";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

const severityColors: Record<string, string> = {
  low: "bg-blue-100 text-blue-800 border-transparent",
  medium: "bg-yellow-100 text-yellow-800 border-transparent",
  high: "bg-orange-100 text-orange-800 border-transparent",
  critical: "bg-red-100 text-red-800 border-transparent",
};

const statusColors: Record<string, string> = {
  open: "bg-red-100 text-red-800 border-transparent",
  investigating: "bg-yellow-100 text-yellow-800 border-transparent",
  resolved: "bg-green-100 text-green-800 border-transparent",
  closed: "bg-gray-100 text-gray-800 border-transparent",
};

export function IncidentList() {
  const { data: incidents, isLoading } = useQuery({
    queryKey: ["incidents"],
    queryFn: getIncidents,
  });

  if (isLoading) {
    return (
      <div className="divide-y">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 p-4">
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-72" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
        ))}
      </div>
    );
  }

  if (!incidents?.length) {
    return (
      <Empty className="py-12">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <AlertCircle />
          </EmptyMedia>
          <EmptyTitle>No incidents yet</EmptyTitle>
          <EmptyDescription>Create one to get started.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="divide-y">
      {incidents.map((incident, i) => (
        <motion.div
          key={incident.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: i * 0.05 }}
        >
          <Link
            to="/incidents/$incidentId"
            params={{ incidentId: incident.id }}
            className="flex items-center gap-4 p-4 transition-colors hover:bg-muted/50"
          >
            <div className="flex-1 space-y-1">
              <p className="font-medium">{incident.title}</p>
              <p className="text-sm text-muted-foreground line-clamp-1">
                {incident.description}
              </p>
            </div>
            <Badge className={severityColors[incident.severity]}>
              {incident.severity}
            </Badge>
            <Badge className={statusColors[incident.status]}>
              {incident.status}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {dayjs(incident.created_at).fromNow()}
            </span>
          </Link>
        </motion.div>
      ))}
    </div>
  );
}
