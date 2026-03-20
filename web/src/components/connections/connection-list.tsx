import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { getServers } from "@/api/servers";
import { getServices } from "@/api/services";
import { listVariants, listItemVariants } from "@/lib/motion";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Cable } from "lucide-react";
import { ServerItem } from "@/components/servers/server-list";
import { ServiceItem } from "@/components/connections/service-list";
import type { Server } from "@/lib/types";
import type { Service } from "@/lib/types";

type ConnectionEntry =
  | { type: "server"; data: Server; created_at: string }
  | { type: "service"; data: Service; created_at: string };

export function ConnectionList() {
  const { data: serversData, isLoading: serversLoading } = useQuery({
    queryKey: ["servers", 1],
    queryFn: () => getServers({ page: 1, page_size: 200 }),
  });

  const { data: servicesData, isLoading: servicesLoading } = useQuery({
    queryKey: ["services", 1],
    queryFn: () => getServices({ page: 1, page_size: 200 }),
  });

  const isLoading = serversLoading || servicesLoading;

  const items = useMemo(() => {
    const result: ConnectionEntry[] = [];
    if (serversData?.items) {
      for (const s of serversData.items) {
        result.push({ type: "server", data: s, created_at: s.created_at });
      }
    }
    if (servicesData?.items) {
      for (const s of servicesData.items) {
        result.push({ type: "service", data: s, created_at: s.created_at });
      }
    }
    result.sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
    return result;
  }, [serversData, servicesData]);

  if (isLoading) {
    return (
      <div className="divide-y">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 p-4">
            <Skeleton className="h-4 w-4 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-8 w-8" />
          </div>
        ))}
      </div>
    );
  }

  if (!items.length) {
    return (
      <Empty className="pb-[20%]">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Cable />
          </EmptyMedia>
          <EmptyTitle>暂无连接</EmptyTitle>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate">
      {items.map((item) =>
        item.type === "server" ? (
          <motion.div key={item.data.id} variants={listItemVariants}>
            <ServerItem server={item.data} />
          </motion.div>
        ) : (
          <motion.div key={item.data.id} variants={listItemVariants}>
            <ServiceItem service={item.data} />
          </motion.div>
        ),
      )}
    </motion.div>
  );
}
