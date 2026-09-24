import type { ButtonHTMLAttributes, ReactNode } from "react";

type ToggleLayout = "row" | "stack";

export function ButtonGrid({
  children,
  columns = 2,
  padded = false,
}: {
  children: ReactNode;
  columns?: number;
  padded?: boolean;
}) {
  return (
    <div
      className={"btn-grid" + (padded ? " btn-grid--padded" : "")}
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {children}
    </div>
  );
}

type ToggleButtonProps = {
  pressed: boolean;
  layout?: ToggleLayout;
  span?: number;
  children: ReactNode;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "type">;

export function ToggleButton({
  pressed,
  layout = "row",
  span,
  className,
  style,
  children,
  disabled,
  ...rest
}: ToggleButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      disabled={disabled}
      className={[
        "toggle-btn",
        layout === "stack" ? "toggle-btn--stack" : "",
        pressed ? "is-active" : "",
        className ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={{
        ...(span ? { gridColumn: `span ${span}` } : {}),
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}
