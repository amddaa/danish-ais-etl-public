// Shared JSX icon re-exports (same lucide set the legacy pages loaded via
// unpkg + createIcons()). For HTML built as plain strings (Leaflet popups),
// use `iconSvg()` with the corresponding icon node from the vanilla `lucide`
// package; it emits the identical inline <svg> createIcons() produced.

export { Anchor as AnchorIcon } from "lucide-react";

// lucide v1 exports each icon as a flat list of shape tuples: [["path", {...}], ...]
type IconNode = [tag: string, attrs: Record<string, string | number>, children?: unknown[]];

const DEFAULT_ATTRS = {
  xmlns: "http://www.w3.org/2000/svg",
  width: 24,
  height: 24,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  "stroke-width": 2,
  "stroke-linecap": "round",
  "stroke-linejoin": "round",
};

function renderNode(node: unknown): string {
  const [tag, attrs, children] = node as IconNode;
  const attrString = Object.entries(attrs)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .map(([k, v]) => `${k}="${v}"`)
    .join(" ");
  const inner = (children ?? []).map(renderNode).join("");
  return `<${tag} ${attrString}>${inner}</${tag}>`;
}

/** Render a lucide icon node as an inline SVG string (createIcons-compatible markup).
 * Returns an empty string for unknown icons, matching legacy createIcons() behavior
 * (e.g. `data-lucide="vessel"`, which does not exist in the icon set).
 * `extraAttrs` are copied onto the <svg> element like createIcons() copied
 * attributes from the source <i> tag. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function iconSvg(iconNode: any, size = 24, extraAttrs?: Record<string, string>): string {
  if (!iconNode) return "";
  const children = iconNode as unknown as IconNode[];
  const node: IconNode = [
    "svg",
    {
      ...DEFAULT_ATTRS,
      width: size,
      height: size,
      ...(extraAttrs ?? {}),
    },
    children,
  ];
  return renderNode(node);
}

/** Escape a value for safe use inside a double-quoted HTML attribute. */
export function escapeAttr(value: unknown): string {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
