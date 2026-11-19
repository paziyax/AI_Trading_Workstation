"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";
import { usePrices } from "@/providers/PricesProvider";
import { useWatchlist } from "@/providers/WatchlistProvider";
import { InlineError } from "./InlineError";
import { PanelSkeleton } from "./PanelSkeleton";
import { WatchlistRow } from "./WatchlistRow";

interface WatchlistPanelProps {
  selectedTicker: string | null;
  onSelect: (ticker: string) => void;
}

export function WatchlistPanel({ selectedTicker, onSelect }: WatchlistPanelProps) {
  const {
    tickers,
    loading,
    error,
    adding,
    addError,
    removeError,
    removing,
    addTicker,
    removeTicker,
    clearAddError,
    refresh,
  } = useWatchlist();
  const { prices, history } = usePrices();
  const [draft, setDraft] = useState("");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const added = await addTicker(draft);
    if (added) setDraft("");
  };

  const handleListKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const current = (event.target as HTMLElement).closest<HTMLElement>(
      "[data-watchlist-row]",
    );
    if (!current) return;
    const rows = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>("[data-watchlist-row]"),
    );
    const index = rows.indexOf(current);
    if (index === -1) return;
    event.preventDefault();
    const next = rows[index + (event.key === "ArrowDown" ? 1 : -1)];
    next?.focus();
  };

  return (
    <section
      className="panel watchlist-panel"
      data-testid="watchlist-panel"
      aria-labelledby="watchlist-title"
      aria-busy={loading}
    >
      <div className="panel-header">
        <h2 className="panel-label" id="watchlist-title">
          Watchlist
        </h2>
        <span className="panel-meta">{tickers.length ? `${tickers.length} tracked` : "—"}</span>
      </div>

      {error ? (
        <div className="panel-banner">
          <InlineError message={error} onRetry={() => void refresh()} compact />
        </div>
      ) : null}
      {removeError ? (
        <div className="panel-banner">
          <InlineError message={removeError} compact />
        </div>
      ) : null}

      {tickers.length > 0 ? (
        <div className="watchlist-columns" aria-hidden="true">
          <span>Ticker</span>
          <span />
          <span className="wc-num">Last</span>
          <span className="wc-num">Chg %</span>
          <span />
        </div>
      ) : null}

      <div className="watchlist-scroll">
        {loading && tickers.length === 0 ? (
          <PanelSkeleton rows={7} label="Loading watchlist" />
        ) : error && tickers.length === 0 ? (
          <div className="panel-empty">
            <p className="empty-title">Watchlist unavailable</p>
            <p className="empty-body">The tickers could not be loaded. Retry above.</p>
          </div>
        ) : tickers.length === 0 ? (
          <div className="panel-empty">
            <p className="empty-title">Nothing on the watchlist</p>
            <p className="empty-body">Add a ticker below to start streaming its price.</p>
          </div>
        ) : (
          <div
            className="watchlist-list"
            role="listbox"
            aria-label="Watchlist tickers"
            aria-orientation="vertical"
            onKeyDown={handleListKeyDown}
          >
            {tickers.map((entry) => (
              <WatchlistRow
                key={entry.ticker}
                entry={entry}
                update={prices[entry.ticker]}
                samples={history[entry.ticker] ?? []}
                selected={entry.ticker === selectedTicker}
                removing={removing.has(entry.ticker)}
                onSelect={onSelect}
                onRemove={(ticker) => void removeTicker(ticker)}
              />
            ))}
          </div>
        )}
      </div>

      <form className="add-ticker" onSubmit={handleSubmit} noValidate>
        <label className="field-label" htmlFor="add-ticker-input">
          Add ticker
        </label>
        <div className="add-ticker-row">
          <input
            id="add-ticker-input"
            data-testid="add-ticker-input"
            className="field-input mono add-ticker-input"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value.toUpperCase());
              if (addError) clearAddError();
            }}
            placeholder="PYPL"
            autoComplete="off"
            spellCheck={false}
            maxLength={10}
            aria-invalid={Boolean(addError)}
            aria-describedby={addError ? "add-ticker-error" : undefined}
          />
          <button
            type="submit"
            className="btn btn-quiet add-ticker-submit"
            data-testid="add-ticker-submit"
            disabled={adding}
            aria-busy={adding}
          >
            {adding ? "Adding…" : "Add"}
          </button>
        </div>
        {addError ? (
          <p className="field-error" id="add-ticker-error" role="alert">
            {addError}
          </p>
        ) : null}
      </form>
    </section>
  );
}
