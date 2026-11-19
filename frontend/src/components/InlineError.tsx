"use client";

import { useState } from "react";

interface InlineErrorProps {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  compact?: boolean;
}

/** Inline, dismissible error banner. Dismissal is scoped to the current message. */
export function InlineError({
  message,
  onRetry,
  retryLabel = "Retry",
  compact = false,
}: InlineErrorProps) {
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);
  if (dismissedFor === message) return null;

  return (
    <div className={compact ? "inline-error is-compact" : "inline-error"} role="alert">
      <span className="inline-error-mark" aria-hidden="true">
        !
      </span>
      <span className="inline-error-text">{message}</span>
      {onRetry ? (
        <button type="button" className="inline-error-action" onClick={onRetry}>
          {retryLabel}
        </button>
      ) : null}
      <button
        type="button"
        className="inline-error-dismiss"
        aria-label="Dismiss error"
        onClick={() => setDismissedFor(message)}
      >
        ×
      </button>
    </div>
  );
}
