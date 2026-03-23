import { useCallback, useState } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  BookOpen,
  Cable,
  ChevronsUpDown,
  LogOut,
  Settings,
  Sparkles,
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
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,

  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { SettingsDialog } from "@/components/settings/settings-dialog";

const mainItems = [
  { to: "/incidents", label: "事件", icon: Activity },
] as const;

const contextItems = [
  { to: "/connections", label: "连接", icon: Cable },
  { to: "/projects", label: "知识库", icon: BookOpen },
] as const;

const navItems = [
  { to: "/skills", label: "技能", icon: Sparkles },
] as const;

export function AppSidebar() {
  const { location } = useRouterState();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);

  const handleLogout = useCallback(() => {
    // TODO: implement logout
    setLogoutOpen(false);
  }, []);

  const renderGroup = (
    items: ReadonlyArray<{
      readonly to: string;
      readonly label: string;
      readonly icon: React.ComponentType<{ className?: string }>;
    }>,
  ) => (
    <SidebarMenu>
      {items.map((item) => {
        const isActive = location.pathname.startsWith(item.to);
        return (
          <SidebarMenuItem key={item.to}>
            <SidebarMenuButton
              isActive={isActive}
              tooltip={item.label}
              render={<Link to={item.to} />}
            >
              <item.icon />
              <span>{item.label}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="flex h-8 items-center px-2">
          <h1 className="text-lg font-semibold">Chronos</h1>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>{renderGroup(mainItems)}</SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>资源</SidebarGroupLabel>
          <SidebarGroupContent>{renderGroup(contextItems)}</SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupContent>{renderGroup(navItems)}</SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
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
                  <AvatarFallback className="rounded-lg">A</AvatarFallback>
                </Avatar>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">Admin</span>
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
            <AlertDialogAction onClick={handleLogout}>
              确认退出
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Sidebar>
  );
}
