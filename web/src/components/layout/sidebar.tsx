import { useCallback, useState } from "react";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useAuthStore } from "@/stores/auth";
import { motion } from "motion/react";
import {
  BookOpen,
  Cable,
  Check,
  ChevronsUpDown,
  Inbox,
  LogOut,
  Monitor,
  Moon,
  Settings,
  Sparkles,
  Sun,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTheme } from "next-themes";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { getAvatarUrl } from "@/api/auth";
import { SettingsDialog } from "@/components/settings/settings-dialog";

const mainItems = [{ to: "/incidents", label: "收件箱", icon: Inbox }] as const;

const contextItems = [
  { to: "/connections", label: "连接", icon: Cable },
  { to: "/projects", label: "知识库", icon: BookOpen },
] as const;

const navItems = [{ to: "/skills", label: "技能", icon: Sparkles }] as const;

function NavItem({
  item,
  isActive,
}: {
  item: {
    readonly to: string;
    readonly label: string;
    readonly icon: React.ComponentType<{ className?: string }>;
  };
  isActive: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <SidebarMenuItem onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
      <SidebarMenuButton isActive={isActive} tooltip={item.label} render={<Link to={item.to} />}>
        <motion.span
          className="inline-flex"
          animate={hovered ? { rotate: [0, -6, 6, -4, 4, -2, 0] } : { rotate: 0 }}
          transition={{ duration: 0.6 }}
        >
          <item.icon />
        </motion.span>
        <span>{item.label}</span>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

export function AppSidebar() {
  const { location } = useRouterState();
  const { state, toggleSidebar } = useSidebar();
  const { theme, setTheme } = useTheme();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();

  const handleLogout = useCallback(() => {
    useAuthStore.getState().clearAuth();
    setLogoutOpen(false);
    navigate({ to: "/login" });
  }, [navigate]);

  const renderGroup = (
    items: ReadonlyArray<{
      readonly to: string;
      readonly label: string;
      readonly icon: React.ComponentType<{ className?: string }>;
    }>,
  ) => (
    <SidebarMenu>
      {items.map((item) => (
        <NavItem key={item.to} item={item} isActive={location.pathname.startsWith(item.to)} />
      ))}
    </SidebarMenu>
  );

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        {state === "collapsed" ? (
          <button onClick={toggleSidebar} className="flex h-8 items-center justify-center">
            <img src="/favicon.png" alt="logo" className="size-5" />
          </button>
        ) : (
          <div className="flex h-8 items-center gap-1">
            <Link to="/incidents" className="flex flex-1 items-center gap-3 px-2 overflow-hidden">
              <img src="/favicon.png" alt="logo" className="size-5 shrink-0" />
              <h1 className="text-base font-medium truncate">Enmolar Chronos</h1>
            </Link>
            <SidebarTrigger className="shrink-0" />
          </div>
        )}
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>{renderGroup(mainItems)}</SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>配置</SidebarGroupLabel>
          <SidebarGroupContent>{renderGroup(contextItems)}</SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupContent>{renderGroup(navItems)}</SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarSeparator className="-mx-2 w-auto!" />
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <SidebarMenuButton
                    size="lg"
                    className="data-[popup-open]:bg-sidebar-accent data-[popup-open]:text-sidebar-accent-foreground"
                  />
                }
              >
                <Avatar className="size-8 rounded-lg">
                  {user?.avatar && (
                    <AvatarImage src={getAvatarUrl(user.avatar)} className="rounded-lg" />
                  )}
                  <AvatarFallback className="rounded-lg">
                    {user?.name?.charAt(0).toUpperCase() ?? "U"}
                  </AvatarFallback>
                </Avatar>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">{user?.name ?? "User"}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {user?.email ?? ""}
                  </span>
                </div>
                <ChevronsUpDown className="ml-auto size-4" />
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="min-w-56 rounded-lg"
                side="top"
                align="end"
                sideOffset={4}
              >
                <DropdownMenuItem onClick={() => setSettingsOpen(true)}>
                  <Settings />
                  设置
                </DropdownMenuItem>
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <Sun className="dark:hidden" />
                    <Moon className="hidden dark:block" />
                    主题
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent>
                    <DropdownMenuItem onClick={() => setTheme("light")}>
                      <Sun />
                      浅色
                      {theme === "light" && <Check className="ml-auto" />}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setTheme("dark")}>
                      <Moon />
                      深色
                      {theme === "dark" && <Check className="ml-auto" />}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setTheme("system")}>
                      <Monitor />
                      跟随系统
                      {theme === "system" && <Check className="ml-auto" />}
                    </DropdownMenuItem>
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setLogoutOpen(true)}>
                  <LogOut />
                  退出登录
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
      <AlertDialog open={logoutOpen} onOpenChange={setLogoutOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认退出登录</AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleLogout}>确认退出</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <SidebarRail />
    </Sidebar>
  );
}
