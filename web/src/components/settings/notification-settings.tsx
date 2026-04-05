import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleHelp, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { client, orpc } from "@/lib/orpc";

const NOTIFICATION_SCENARIOS = [
  { title: "新事件创建", description: "当创建新的事件时，发送通知" },
  { title: "状态变更", description: "事件状态变更时发送通知" },
  { title: "需要人工输入", description: "当 Agent 需要人工补充信息时发送通知" },
  { title: "需要审批", description: "当 Agent 执行高风险操作需要审批时发送通知" },
];

export function NotificationSettings() {
  const queryClient = useQueryClient();
  const [platform, setPlatform] = useState("feishu");
  const [draft, setDraft] = useState({ webhookUrl: "", signKey: "", enabled: true });
  const [testing, setTesting] = useState(false);
  const [initialized, setInitialized] = useState(false);

  const { data: settings, isLoading } = useQuery(orpc.notification.get.queryOptions({
    input: { platform },
  }));

  useEffect(() => {
    if (settings && !initialized) {
      setDraft({
        webhookUrl: settings.webhookUrl ?? "",
        signKey: settings.signKey ?? "",
        enabled: settings.enabled ?? true,
      });
      setInitialized(true);
    } else if (!settings && !isLoading && !initialized) {
      setDraft({ webhookUrl: "", signKey: "", enabled: true });
      setInitialized(true);
    }
  }, [settings, isLoading, initialized]);

  useEffect(() => {
    setInitialized(false);
  }, [platform]);

  const updateMutation = useMutation({
    mutationFn: (data: { webhookUrl: string; signKey?: string; enabled: boolean }) =>
      client.notification.upsert({ platform, ...data }),
    onSuccess: () => {
      toast.success("保存成功");
      queryClient.invalidateQueries({ queryKey: orpc.notification.get.key({ input: { platform } }) });
    },
  });

  const handleSave = () => {
    updateMutation.mutate({
      webhookUrl: draft.webhookUrl,
      signKey: draft.signKey || undefined,
      enabled: draft.enabled,
    });
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await client.notification.testWebhook({
        webhookUrl: draft.webhookUrl,
        signKey: draft.signKey || undefined,
      });
      if (result.success) {
        toast.success("测试消息发送成功");
      } else {
        toast.error("测试消息发送失败", { description: result.message });
      }
    } catch (err) {
      toast.error("测试消息发送失败", {
        description: err instanceof Error ? err.message : "未知错误",
      });
    } finally {
      setTesting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="text-muted-foreground size-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-medium">通知</h3>
          <Tooltip>
            <TooltipTrigger render={<CircleHelp className="text-muted-foreground size-4 cursor-help" />} />
            <TooltipContent side="right" className="block max-w-xs space-y-2 py-2">
              <p className="font-medium">通知触发场景</p>
              <ul className="space-y-2">
                {NOTIFICATION_SCENARIOS.map((s) => (
                  <li key={s.title}>
                    <p className="text-xs font-medium">{s.title}</p>
                    <p className="text-[11px] opacity-70">{s.description}</p>
                  </li>
                ))}
              </ul>
            </TooltipContent>
          </Tooltip>
        </div>
        <p className="text-muted-foreground text-sm">配置事件通知集成</p>
      </div>
      <Separator />
      <div className="space-y-4">
        <div className="grid gap-2">
          <Label>集成平台</Label>
          <Select value={platform} onValueChange={(v) => v !== null && setPlatform(v)}>
            <SelectTrigger className="w-full">
              <SelectValue>{platform === "feishu" ? "飞书" : platform}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="feishu">飞书</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {platform === "feishu" && (
          <>
            <div className="flex items-center justify-between">
              <Label>启用通知</Label>
              <Switch
                checked={draft.enabled}
                onCheckedChange={(checked) => setDraft((d) => ({ ...d, enabled: checked }))}
              />
            </div>

            <div className="grid gap-2">
              <Label>
                Webhook URL <span className="text-destructive">*</span>
              </Label>
              <Input
                value={draft.webhookUrl}
                onChange={(e) => setDraft((d) => ({ ...d, webhookUrl: e.target.value }))}
                placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
              />
              <p className="text-muted-foreground text-xs">飞书自定义机器人的 Webhook 地址</p>
            </div>
            <div className="grid gap-2">
              <Label>签名密钥</Label>
              <Input
                type="password"
                value={draft.signKey}
                onChange={(e) => setDraft((d) => ({ ...d, signKey: e.target.value }))}
                placeholder="可选，用于 HMAC-SHA256 签名验证"
              />
              <p className="text-muted-foreground text-xs">
                飞书机器人安全设置中的 Sign Key，留空则不启用签名校验
              </p>
            </div>
          </>
        )}

        <div className="flex gap-2 pt-2">
          <Button
            variant="outline"
            onClick={handleTest}
            disabled={!draft.webhookUrl.trim() || testing}
          >
            {testing && <Loader2 className="animate-spin" />}
            测试
          </Button>
          <Button onClick={handleSave} disabled={!draft.webhookUrl.trim() || updateMutation.isPending}>
            {updateMutation.isPending && <Loader2 className="animate-spin" />}
            保存
          </Button>
        </div>
      </div>
    </div>
  );
}
