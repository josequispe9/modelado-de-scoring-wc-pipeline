import * as React from "react"
import { cn } from "@/lib/utils"

// ── Context ────────────────────────────────────────────────────────────────────

type SidebarState = "expanded" | "collapsed"

const SidebarContext = React.createContext<{
  state: SidebarState
  toggle: () => void
}>({ state: "expanded", toggle: () => {} })

export function useSidebar() {
  return React.useContext(SidebarContext)
}

// ── Provider ───────────────────────────────────────────────────────────────────

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<SidebarState>("expanded")
  const toggle = () => setState((s) => (s === "expanded" ? "collapsed" : "expanded"))
  return (
    <SidebarContext.Provider value={{ state, toggle }}>
      <div className="flex h-screen w-full overflow-hidden">{children}</div>
    </SidebarContext.Provider>
  )
}

// ── Trigger ────────────────────────────────────────────────────────────────────

export function SidebarTrigger({ className }: { className?: string }) {
  const { toggle } = useSidebar()
  return (
    <button onClick={toggle} className={cn("p-1 rounded hover:bg-muted", className)} type="button">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <line x1="3" y1="6" x2="21" y2="6" />
        <line x1="3" y1="12" x2="21" y2="12" />
        <line x1="3" y1="18" x2="21" y2="18" />
      </svg>
    </button>
  )
}

// ── Sidebar ────────────────────────────────────────────────────────────────────

export function Sidebar({ children, className, collapsible: _c }: { children: React.ReactNode; className?: string; collapsible?: string }) {
  const { state } = useSidebar()
  return (
    <aside
      className={cn(
        "flex flex-col h-full bg-sidebar border-r border-sidebar-border transition-all duration-200 overflow-hidden",
        state === "collapsed" ? "w-12" : "w-56",
        className
      )}
    >
      {children}
    </aside>
  )
}

export function SidebarContent({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("flex flex-col flex-1 overflow-y-auto", className)}>{children}</div>
}

export function SidebarGroup({ children }: { children: React.ReactNode }) {
  return <div className="px-2 py-1">{children}</div>
}

export function SidebarGroupLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("px-2 py-1 text-xs font-medium text-muted-foreground", className)}>{children}</p>
}

export function SidebarGroupContent({ children }: { children: React.ReactNode }) {
  return <div>{children}</div>
}

export function SidebarMenu({ children }: { children: React.ReactNode }) {
  return <ul className="space-y-0.5">{children}</ul>
}

export function SidebarMenuItem({ children }: { children: React.ReactNode }) {
  return <li>{children}</li>
}

export function SidebarMenuButton({
  children,
  className,
  asChild,
  ...props
}: {
  children: React.ReactNode
  className?: string
  asChild?: boolean
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  if (asChild) {
    return <div className={cn("flex items-center gap-2 px-2 py-1.5 rounded text-sm w-full", className)}>{children}</div>
  }
  return (
    <button
      className={cn("flex items-center gap-2 px-2 py-1.5 rounded text-sm w-full text-left", className)}
      {...props}
    >
      {children}
    </button>
  )
}

export function SidebarMenuSub({ children }: { children: React.ReactNode }) {
  return <ul className="ml-4 space-y-0.5 mt-0.5">{children}</ul>
}

export function SidebarMenuSubItem({ children }: { children: React.ReactNode }) {
  return <li>{children}</li>
}
