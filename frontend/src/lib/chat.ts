import { formatPrice, formatQuantity } from "./format";
import type { ChatActions } from "./types";

export interface ActionChip {
  key: string;
  label: string;
  detail?: string;
  status: "executed" | "failed";
}

/** Human sentences for the actions the assistant executed. */
export function chatActionChips(actions: ChatActions | null | undefined): ActionChip[] {
  if (!actions) return [];
  const chips: ActionChip[] = [];

  (actions.trades ?? []).forEach((trade, index) => {
    if (trade.status === "failed") {
      chips.push({
        key: `trade-${index}`,
        label: `Failed: ${trade.error?.trim() || `${trade.side} ${trade.ticker}`}`,
        status: "failed",
      });
      return;
    }
    chips.push({
      key: `trade-${index}`,
      label: `${trade.side === "buy" ? "Bought" : "Sold"} ${formatQuantity(trade.quantity)} ${trade.ticker}`,
      detail: trade.price != null ? `at ${formatPrice(trade.price)}` : undefined,
      status: "executed",
    });
  });

  (actions.watchlist_changes ?? []).forEach((change, index) => {
    if (change.status === "failed") {
      chips.push({
        key: `watch-${index}`,
        label: `Failed: ${change.error?.trim() || `${change.action} ${change.ticker}`}`,
        status: "failed",
      });
      return;
    }
    chips.push({
      key: `watch-${index}`,
      label: `${change.action === "add" ? "Added" : "Removed"} ${change.ticker}`,
      status: "executed",
    });
  });

  return chips;
}
