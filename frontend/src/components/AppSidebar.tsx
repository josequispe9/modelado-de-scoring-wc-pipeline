import { Activity, BarChart2, Database, Globe, Settings, Monitor, ChevronDown } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { cn } from "@/lib/utils";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";

const mainNav = [
  {
    title: "Pipeline",
    icon: Activity,
    children: [
      { title: "Monitoreo",      url: "/pipeline/monitoreo",      icon: Monitor   },
      { title: "Estadísticas",  url: "/pipeline/estadisticas",  icon: BarChart2 },
      { title: "Configuración",  url: "/pipeline/configuracion",  icon: Settings  },
    ],
  },
  {
    title: "Scraping",
    icon: Globe,
    url: "/scraping",
  },
  {
    title: "Bases",
    icon: Database,
    url: "/bases",
  },
];

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed  = state === "collapsed";
  const location   = useLocation();
  const navigate   = useNavigate();

  const isPipelineActive = mainNav[0].children!.some(c =>
    location.pathname.startsWith(c.url)
  );
  const [pipelineOpen, setPipelineOpen] = useState(isPipelineActive);

  const btnBase =
    "flex items-center gap-2 w-full rounded-md px-2 py-1.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent transition-colors cursor-pointer";

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarContent className="pt-4">

        {/* Logo */}
        {!collapsed && (
          <div className="px-4 pb-4 mb-2 border-b border-sidebar-border">
            <h1 className="text-sm font-semibold tracking-wide text-primary">
              DATA<span className="text-sidebar-foreground">OPS</span>
            </h1>
            <p className="text-[10px] text-muted-foreground mt-0.5 font-mono">Panel de Control</p>
          </div>
        )}

        <SidebarGroup>
          {!collapsed && (
            <SidebarGroupLabel className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Módulos
            </SidebarGroupLabel>
          )}
          <SidebarGroupContent>
            <SidebarMenu>

              {/* Pipeline — colapsable con hijos */}
              <SidebarMenuItem>
                <button
                  type="button"
                  onClick={() => !collapsed && setPipelineOpen(o => !o)}
                  className={cn(btnBase, isPipelineActive && "text-primary font-medium")}
                >
                  <Activity className="h-4 w-4 shrink-0 text-primary" />
                  {!collapsed && (
                    <>
                      <span className="flex-1 text-left">Pipeline</span>
                      <ChevronDown
                        className={cn(
                          "h-3 w-3 shrink-0 text-muted-foreground transition-transform",
                          pipelineOpen && "rotate-180"
                        )}
                      />
                    </>
                  )}
                </button>

                {!collapsed && pipelineOpen && (
                  <div className="ml-4 mt-0.5 flex flex-col gap-0.5 border-l border-sidebar-border pl-3">
                    {mainNav[0].children!.map(child => {
                      const active = location.pathname.startsWith(child.url);
                      return (
                        <button
                          key={child.url}
                          type="button"
                          onClick={() => navigate(child.url)}
                          className={cn(
                            btnBase,
                            active
                              ? "bg-sidebar-accent text-primary font-medium"
                              : "text-sidebar-foreground"
                          )}
                        >
                          <child.icon className="h-3.5 w-3.5 shrink-0" />
                          <span>{child.title}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </SidebarMenuItem>

              {/* Scraping y Bases — sin hijos */}
              {mainNav.slice(1).map(item => {
                const active = location.pathname.startsWith(item.url!);
                return (
                  <SidebarMenuItem key={item.title}>
                    <button
                      type="button"
                      onClick={() => navigate(item.url!)}
                      className={cn(
                        btnBase,
                        active
                          ? "bg-sidebar-accent text-primary font-medium"
                          : "text-sidebar-foreground"
                      )}
                    >
                      <item.icon className="h-4 w-4 shrink-0 text-primary" />
                      {!collapsed && <span>{item.title}</span>}
                    </button>
                  </SidebarMenuItem>
                );
              })}

            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

      </SidebarContent>
    </Sidebar>
  );
}
