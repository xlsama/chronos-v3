import { useEffect, useRef, useState } from "react";
import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
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
  const videoRef = useRef<HTMLVideoElement>(null);
  const reduceMotion = useReducedMotion();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  // 与标题流光同步：200ms 后启动视频播放（reduce-motion 时立即启动）。
  useEffect(() => {
    if (reduceMotion) {
      videoRef.current?.play().catch(() => {});
      return;
    }
    const timer = window.setTimeout(() => {
      videoRef.current?.play().catch(() => {});
    }, 200);
    return () => window.clearTimeout(timer);
  }, [reduceMotion]);

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
    <div className="min-h-screen bg-background">
      <div className="flex min-h-screen w-full flex-col px-6 py-6 md:px-12 md:py-10 lg:px-20 xl:px-24">
        {/* 顶部 Logo */}
        <header className="flex items-center">
          <img src={logoSvg} alt="Chronos" className="h-6" />
        </header>

        {/* 主内容：左列(标题+简介+视频) / 右列(表单) */}
        <div className="flex flex-1 items-center py-10">
          <div className="grid w-full -translate-y-[8vh] grid-cols-1 gap-10 md:grid-cols-[2.5fr_2fr] md:gap-12 lg:gap-16">
            {/* 左列：标题 + 简介 + 视频（仅 md+ 显示） */}
            <div className="hidden flex-col gap-8 md:flex md:pl-8 lg:gap-10 lg:pl-12 xl:pl-16">
              <div className="space-y-6">
                <h2 className="text-4xl font-bold uppercase leading-tight tracking-tight lg:text-5xl">
                  <span className="inline-grid">
                    {/* 原色文字（始终展示） */}
                    <span className="col-start-1 row-start-1">
                      OPS{" "}
                      <span className="bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 bg-clip-text text-transparent">
                        AI Agent
                      </span>
                    </span>
                    {/* 流光叠加层 */}
                    {!reduceMotion && (
                      <motion.span
                        aria-hidden="true"
                        className="pointer-events-none col-start-1 row-start-1"
                        style={{
                          backgroundImage:
                            "linear-gradient(110deg, transparent 35%, rgba(255, 255, 255, 0.9) 50%, transparent 65%)",
                          backgroundSize: "200% 100%",
                          backgroundRepeat: "no-repeat",
                          WebkitBackgroundClip: "text",
                          backgroundClip: "text",
                          color: "transparent",
                        }}
                        initial={{ backgroundPositionX: "150%" }}
                        animate={{ backgroundPositionX: "-50%" }}
                        transition={{
                          delay: 0.2,
                          duration: 1.2,
                          ease: "linear",
                        }}
                      >
                        OPS AI Agent
                      </motion.span>
                    )}
                  </span>
                </h2>
                <p className="text-base text-muted-foreground lg:text-lg">
                  自主诊断、定位与修复线上故障，让 Chronos 成为你 24/7 的运维伙伴。
                </p>
              </div>
              <div className="overflow-hidden rounded-2xl border border-border shadow-sm">
                <video
                  ref={videoRef}
                  src="/login-hero.mp4"
                  loop
                  muted
                  playsInline
                  preload="auto"
                  className="aspect-video w-full object-cover"
                />
              </div>
            </div>

            {/* 右列：表单（垂直居中于左列总高度） */}
            <div className="flex items-center justify-center">
              <div className="w-full max-w-sm">
                <h1 className="mb-6 text-base font-semibold text-foreground">
                  {mode === "login" ? "登录 Chronos" : "创建 Chronos 账号"}
                </h1>

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
          </div>
        </div>
      </div>
    </div>
  );
}
