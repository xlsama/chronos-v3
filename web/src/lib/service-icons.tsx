import { Database } from "lucide-react";
import { cn } from "@/lib/utils";

import mysqlIcon from "@/assets/icons/services/mysql.svg";
import postgresqlIcon from "@/assets/icons/services/postgresql.svg";
import redisIcon from "@/assets/icons/services/redis.svg";
import prometheusIcon from "@/assets/icons/services/prometheus.svg";
import mongodbIcon from "@/assets/icons/services/mongodb.svg";
import elasticsearchIcon from "@/assets/icons/services/elasticsearch.svg";
import jenkinsIcon from "@/assets/icons/services/jenkins.svg";

const serviceIconMap: Record<string, string> = {
  mysql: mysqlIcon,
  postgresql: postgresqlIcon,
  redis: redisIcon,
  prometheus: prometheusIcon,
  mongodb: mongodbIcon,
  elasticsearch: elasticsearchIcon,
  jenkins: jenkinsIcon,
};

export function ServiceIcon({
  serviceType,
  className = "h-5 w-5",
}: {
  serviceType: string;
  className?: string;
}) {
  const iconUrl = serviceIconMap[serviceType];
  if (!iconUrl)
    return (
      <Database className={cn(className, "text-muted-foreground")} />
    );
  return <img src={iconUrl} alt={serviceType} className={className} />;
}
