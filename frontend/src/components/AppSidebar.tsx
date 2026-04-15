import { Activity, Database, Globe, Settings, Monitor, ChevronDown } from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { useLocation } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

const mainNav = [
  {
    title: "Pipeline",
    icon: Activity,
    children: [
      { title: "Monitoreo", url: "/pipeline/monitoreo", icon: Monitor },
      { title: "Configuración", url: "/pipeline/configuracion", icon: Settings },
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
  const collapsed = state === "collapsed";
  const location = useLocation();

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarContent className="pt-4">
        {!collapsed && (
          <div className="px-4 pb-4 mb-2 border-b border-sidebar-border">
            <h1 className="text-sm font-semibold tracking-wide text-primary">
              DATA<span className="text-sidebar-foreground">OPS</span>
            </h1>
            <p className="text-[10px] text-muted-foreground mt-0.5 font-mono">Panel de Control</p>
          </div>
        )}
        <SidebarGroup>
          <SidebarGroupLabel className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Módulos
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {mainNav.map((item) =>
                item.children ? (
                  <Collapsible
                    key={item.title}
                    defaultOpen={item.children.some((c) => location.pathname.startsWith(c.url))}
                  >
                    <SidebarMenuItem>
                      <CollapsibleTrigger asChild>
                        <SidebarMenuButton className="hover:bg-sidebar-accent">
                          <item.icon className="h-4 w-4 text-primary" />
                          {!collapsed && (
                            <>
                              <span className="flex-1">{item.title}</span>
                              <ChevronDown className="h-3 w-3 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
                            </>
                          )}
                        </SidebarMenuButton>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <SidebarMenuSub>
                          {item.children.map((child) => (
                            <SidebarMenuSubItem key={child.url}>
                              <SidebarMenuButton asChild>
                                <NavLink
                                  to={child.url}
                                  end
                                  className="hover:bg-sidebar-accent text-sidebar-foreground"
                                  activeClassName="bg-sidebar-accent text-primary font-medium"
                                >
                                  <child.icon className="h-3.5 w-3.5 mr-2" />
                                  {!collapsed && <span className="text-sm">{child.title}</span>}
                                </NavLink>
                              </SidebarMenuButton>
                            </SidebarMenuSubItem>
                          ))}
                        </SidebarMenuSub>
                      </CollapsibleContent>
                    </SidebarMenuItem>
                  </Collapsible>
                ) : (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton asChild>
                      <NavLink
                        to={item.url}
                        className="hover:bg-sidebar-accent text-sidebar-foreground"
                        activeClassName="bg-sidebar-accent text-primary font-medium"
                      >
                        <item.icon className="h-4 w-4 text-primary" />
                        {!collapsed && <span>{item.title}</span>}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
