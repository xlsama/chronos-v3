import { Link, useRouterState } from "@tanstack/react-router";
import { Activity, LayoutGrid, Library, Sparkles } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

const mainItems = [
  { to: "/incidents", label: "事件", icon: Activity },
] as const;

const contextItems = [
  { to: "/infrastructure", label: "基础设施", icon: LayoutGrid },
  { to: "/projects", label: "知识库", icon: Library },
] as const;

const bottomItems = [
  { to: "/skills", label: "技能", icon: Sparkles },
] as const;

export function AppSidebar() {
  const { location } = useRouterState();

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
          <SidebarGroupLabel>上下文</SidebarGroupLabel>
          <SidebarGroupContent>{renderGroup(contextItems)}</SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupContent>{renderGroup(bottomItems)}</SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
