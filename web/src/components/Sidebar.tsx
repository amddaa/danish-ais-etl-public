import type { ReactNode } from "react";

export function Sidebar({ children }: { children: ReactNode }) {
  return <aside id="sidebar">{children}</aside>;
}

export function SidebarHeader({ title }: { title: string }) {
  return (
    <header className="sidebar-header">
      <h1>{title}</h1>
    </header>
  );
}

export function SidebarBody({ children }: { children: ReactNode }) {
  return <div className="controls">{children}</div>;
}
