"use client";

import type { KeyboardEvent } from "react";
import { formatPrice, formatPercent, trendOf } from "@/lib/format";
import type { PriceUpdate, WatchlistTicker } from "@/lib/types";
import { usePriceFlash } from "@/hooks/usePriceFlash";
import { Sparkline } from "./Sparkline";

interface WatchlistRowProps {
  entry: WatchlistTicker;
  update?: PriceUpdate;
  samples: number[];
  selected: boolean;
  removing: boolean;
  onSelect: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}

export function WatchlistRow({
  entry,
  update,
  samples,
  selected,
  removing,
  onSelect,
  onRemove,
}: WatchlistRowProps) {
  const price = update?.price ?? entry.price;
  const open = entry.open_price ?? samples[0] ?? null;
  const change = price !== null && open !== null && open !== 0 ? price - open : entry.change;
  const changePct =
    price !== null && open !== null && open !== 0 ? (change! / open) * 100 : entry.change_pct;
  const trend = trendOf(changePct);
  const flash = usePriceFlash(price);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(entry.ticker);
    }
  };

  return (
    <div
      className="watchlist-row"
      role="option"
      aria-selected={selected}
      tabIndex={0}
      data-testid={`watchlist-row-${entry.ticker}`}
      data-watchlist-row="true"
      data-selected={selected}
      onClick={() => onSelect(entry.ticker)}
      onKeyDown={handleKeyDown}
    >
      <span className="watchlist-ticker mono">{entry.ticker}</span>
      <Sparkline ticker={entry.ticker} samples={samples} tone={trend} width={50} />
      <span
        className="watchlist-price mono"
        data-testid={`watchlist-price-${entry.ticker}`}
        data-flash={flash}
      >
        {formatPrice(price)}
      </span>
      <span
        className={`watchlist-change mono is-${trend}`}
        data-testid={`watchlist-change-${entry.ticker}`}
        title={change !== null ? `Session change ${formatPrice(change)}` : undefined}
      >
        {formatPercent(changePct)}
      </span>
      <button
        type="button"
        className="row-remove"
        data-testid={`remove-ticker-${entry.ticker}`}
        aria-label={`Remove ${entry.ticker} from watchlist`}
        title={`Remove ${entry.ticker}`}
        disabled={removing}
        onClick={(event) => {
          event.stopPropagation();
          onRemove(entry.ticker);
        }}
        onKeyDown={(event) => event.stopPropagation()}
      >
        ×
      </button>
    </div>
  );
}
