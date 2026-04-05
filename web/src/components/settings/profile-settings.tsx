import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Camera, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { getAvatarUrl, uploadAvatar } from "@/api/auth";
import { client } from "@/lib/orpc";
import { useAuthStore } from "@/stores/auth";

export function ProfileSettings() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [passwords, setPasswords] = useState({
    oldPassword: "",
    newPassword: "",
    confirmPassword: "",
  });

  const avatarMutation = useMutation({
    mutationFn: uploadAvatar,
    onSuccess: (updatedUser) => {
      setUser(updatedUser);
      toast.success("头像更新成功");
    },
  });

  const passwordMutation = useMutation({
    mutationFn: (data: { oldPassword: string; newPassword: string }) => client.auth.changePassword(data),
    onSuccess: () => {
      toast.success("密码修改成功");
      setPasswords({ oldPassword: "", newPassword: "", confirmPassword: "" });
    },
  });

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error("头像文件不能超过 5MB");
      return;
    }
    avatarMutation.mutate(file);
    e.target.value = "";
  };

  const handlePasswordSubmit = () => {
    if (passwords.newPassword !== passwords.confirmPassword) {
      toast.error("两次输入的新密码不一致");
      return;
    }
    if (passwords.newPassword.length < 6) {
      toast.error("新密码长度至少 6 位");
      return;
    }
    passwordMutation.mutate({
      oldPassword: passwords.oldPassword,
      newPassword: passwords.newPassword,
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium">个人资料</h3>
        <p className="text-muted-foreground text-sm">管理您的头像和密码</p>
      </div>
      <Separator />

      <div className="space-y-4">
        <Label>头像</Label>
        <div className="flex items-center gap-4">
          <div
            className="relative group cursor-pointer"
            onClick={() => fileInputRef.current?.click()}
          >
            <Avatar className="size-16">
              {user?.avatar && (
                <AvatarImage src={getAvatarUrl(user.avatar)} />
              )}
              <AvatarFallback className="text-lg">
                {user?.name?.charAt(0).toUpperCase() ?? "U"}
              </AvatarFallback>
            </Avatar>
            <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity">
              {avatarMutation.isPending ? (
                <Loader2 className="size-5 text-white animate-spin" />
              ) : (
                <Camera className="size-5 text-white" />
              )}
            </div>
          </div>
          <div className="text-sm text-muted-foreground">
            <p>点击头像更换</p>
            <p>支持 PNG、JPG、WebP，最大 5MB</p>
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".png,.jpg,.jpeg,.webp"
          onChange={handleAvatarChange}
        />
      </div>

      <Separator />

      <div className="space-y-4">
        <Label className="text-base font-medium">修改密码</Label>
        <div className="grid gap-3 max-w-sm">
          <div className="grid gap-2">
            <Label>当前密码</Label>
            <Input
              type="password"
              value={passwords.oldPassword}
              onChange={(e) =>
                setPasswords((p) => ({ ...p, oldPassword: e.target.value }))
              }
              placeholder="请输入当前密码"
            />
          </div>
          <div className="grid gap-2">
            <Label>新密码</Label>
            <Input
              type="password"
              value={passwords.newPassword}
              onChange={(e) =>
                setPasswords((p) => ({ ...p, newPassword: e.target.value }))
              }
              placeholder="至少 6 位"
            />
          </div>
          <div className="grid gap-2">
            <Label>确认新密码</Label>
            <Input
              type="password"
              value={passwords.confirmPassword}
              onChange={(e) =>
                setPasswords((p) => ({ ...p, confirmPassword: e.target.value }))
              }
              placeholder="再次输入新密码"
            />
          </div>
        </div>
        <Button
          onClick={handlePasswordSubmit}
          disabled={
            !passwords.oldPassword ||
            !passwords.newPassword ||
            !passwords.confirmPassword ||
            passwordMutation.isPending
          }
        >
          {passwordMutation.isPending && <Loader2 className="animate-spin" />}
          修改密码
        </Button>
      </div>
    </div>
  );
}
