import type { ReactNode } from "react";

export function PanelSkeleton({
  rows = 4,
  label = "Loading",
  meta,
}: {
  rows?: number;
  label?: string;
  meta?: ReactNode;
}) {
  return (
    <div className="skeleton-panel" role="status" aria-label={label}>
      <span className="sr-only">{label}</span>
      {meta}
      <div className="skeleton-stack" aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <div className="skeleton-row" key={index}>
            <span className="skeleton-block" style={{ width: `${34 + ((index * 17) % 38)}%` }} />
            <span className="skeleton-block" style={{ width: `${14 + ((index * 11) % 20)}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}
