import { Link, useMatch, useResolvedPath } from "react-router-dom"
import { cn } from "@/lib/utils"

interface NavLinkProps {
  to: string
  end?: boolean
  className?: string
  activeClassName?: string
  children: React.ReactNode
}

export function NavLink({ to, end, className, activeClassName, children }: NavLinkProps) {
  const resolved = useResolvedPath(to)
  const match = useMatch({ path: resolved.pathname, end: end ?? false })

  return (
    <Link to={to} className={cn(className, match ? activeClassName : "")}>
      {children}
    </Link>
  )
}
