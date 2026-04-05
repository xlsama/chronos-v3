import { useState } from "react";
import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/stores/auth";
import { client } from "@/lib/orpc";
import logoSvg from "@/assets/img/logo.svg";

export const Route = createFileRoute("/login")({
  beforeLoad: () => {
    const token = useAuthStore.getState().token || useAuthStore.getState().hydrate();
    if (token) {
      throw redirect({ to: "/incidents" });
    }
  },
  component: LoginPage,
});

function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = () => {
    const errs: Record<string, string> = {};
    if (!email.trim()) {
      errs.email = "请输入邮箱";
    }
    if (password.length < 6) {
      errs.password = "密码至少需要 6 个字符";
    }
    if (mode === "register" && !name.trim()) {
      errs.name = "请输入姓名";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const loginMutation = useMutation({
    mutationFn: (data: { email: string; password: string }) => client.auth.login(data),
    onSuccess: async (data) => {
      useAuthStore.getState().setAuth({ id: "", email: "", name: "", avatar: null, isActive: true, createdAt: "" }, data.accessToken);
      try {
        const me = await client.auth.me();
        useAuthStore.getState().setAuth(me, data.accessToken);
        navigate({ to: "/incidents" });
      } catch {
        useAuthStore.getState().clearAuth();
        toast.error("获取用户信息失败");
      }
    },
  });

  const registerMutation = useMutation({
    mutationFn: (data: { email: string; password: string; name: string }) => client.auth.register(data),
    onSuccess: () => {
      toast.success("注册成功，请登录");
      setMode("login");
      setName("");
      setErrors({});
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    if (mode === "login") {
      loginMutation.mutate({ email, password });
    } else {
      registerMutation.mutate({ email, password, name });
    }
  };

  const isLoading = loginMutation.isPending || registerMutation.isPending;

  const clearError = (field: string) => {
    if (errors[field]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background">
      {/* Top-left logo */}
      <div className="absolute left-8 top-6 flex items-center gap-3">
        <img src={logoSvg} alt="Chronos" className="h-6" />
      </div>

      {/* Center form */}
      <div className="w-full max-w-sm px-6">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold tracking-tight">
            Welcome to Chronos
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {mode === "login"
              ? "登录以继续使用"
              : "创建账号以开始使用"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {mode === "register" && (
            <Field data-invalid={!!errors.name || undefined}>
              <Label htmlFor="name">姓名</Label>
              <Input
                id="name"
                type="text"
                placeholder="请输入姓名"
                value={name}
                onChange={(e) => { setName(e.target.value); clearError("name"); }}
                autoComplete="name"
                aria-invalid={!!errors.name}
              />
              <FieldError>{errors.name}</FieldError>
            </Field>
          )}

          <Field data-invalid={!!errors.email || undefined}>
            <Label htmlFor="email">邮箱</Label>
            <Input
              id="email"
              type="email"
              placeholder="请输入邮箱"
              value={email}
              onChange={(e) => { setEmail(e.target.value); clearError("email"); }}
              autoFocus
              autoComplete="email"
              aria-invalid={!!errors.email}
            />
            <FieldError>{errors.email}</FieldError>
          </Field>

          <Field data-invalid={!!errors.password || undefined}>
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              type="password"
              placeholder="请输入密码"
              value={password}
              onChange={(e) => { setPassword(e.target.value); clearError("password"); }}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              aria-invalid={!!errors.password}
            />
            <FieldError>{errors.password}</FieldError>
          </Field>

          <Button
            type="submit"
            className="h-11 w-full text-base"
            disabled={isLoading}
          >
            {isLoading && <Loader2 className="mr-2 size-4 animate-spin" />}
            {mode === "login" ? "登录" : "注册"}
          </Button>
        </form>

        <div className="mt-6 text-center text-sm text-muted-foreground">
          {mode === "login" ? (
            <>
              还没有账号？{" "}
              <button
                type="button"
                className="font-medium text-foreground underline-offset-4 hover:underline"
                onClick={() => { setMode("register"); setErrors({}); }}
              >
                注册
              </button>
            </>
          ) : (
            <>
              已有账号？{" "}
              <button
                type="button"
                className="font-medium text-foreground underline-offset-4 hover:underline"
                onClick={() => { setMode("login"); setErrors({}); }}
              >
                登录
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
