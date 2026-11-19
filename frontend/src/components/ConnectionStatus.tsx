import type { ConnectionState } from "@/lib/types";

export const CONNECTION_META: Record<
  ConnectionState,
  { label: string; description: string }
> = {
  connected: { label: "Live", description: "Market stream connected" },
  reconnecting: { label: "Reconnecting", description: "Reconnecting to the market stream" },
  disconnected: { label: "Offline", description: "Market stream is offline" },
};

export function ConnectionStatus({ state }: { state: ConnectionState }) {
  const meta = CONNECTION_META[state];

  return (
    <div
      className="connection"
      data-testid="connection-status"
      data-state={state}
      title={meta.description}
    >
      <span className="connection-dot" aria-hidden="true" />
      <span className="connection-label" role="status" aria-live="polite">
        {meta.label}
      </span>
    </div>
  );
}
