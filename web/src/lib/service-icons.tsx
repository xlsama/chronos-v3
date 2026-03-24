import { Database } from "lucide-react";
import { cn } from "@/lib/utils";

import mysqlIcon from "@/assets/icons/services/mysql.svg";
import postgresqlIcon from "@/assets/icons/services/postgresql.svg";
import redisIcon from "@/assets/icons/services/redis.svg";
import prometheusIcon from "@/assets/icons/services/prometheus.svg";
import mongodbIcon from "@/assets/icons/services/mongodb.svg";
import elasticsearchIcon from "@/assets/icons/services/elasticsearch.svg";
import jenkinsIcon from "@/assets/icons/services/jenkins.svg";
import dockerIcon from "@/assets/icons/services/docker.svg";
import kubernetesIcon from "@/assets/icons/services/kubernetes.svg";
import hiveIcon from "@/assets/icons/services/hive.svg";
import dorisIcon from "@/assets/icons/services/doris.svg";
import starrocksIcon from "@/assets/icons/services/starrocks.svg";
import kettleIcon from "@/assets/icons/services/kettle.svg";

const serviceIconMap: Record<string, string> = {
  mysql: mysqlIcon,
  postgresql: postgresqlIcon,
  redis: redisIcon,
  prometheus: prometheusIcon,
  mongodb: mongodbIcon,
  elasticsearch: elasticsearchIcon,
  jenkins: jenkinsIcon,
  docker: dockerIcon,
  kubernetes: kubernetesIcon,
  hive: hiveIcon,
  doris: dorisIcon,
  starrocks: starrocksIcon,
  kettle: kettleIcon,
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
