import type { ReactNode } from "react";

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="section-title">{children}</h2>;
}

export function SidebarSectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="section-title section-title--flush">{children}</h2>;
}
