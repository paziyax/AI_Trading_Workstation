"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { executeTrade, toErrorMessage } from "@/lib/api";
import { formatCurrency, formatPrice } from "@/lib/format";
import type { TradeSide } from "@/lib/types";
import {
  isValidTicker,
  normalizeTicker,
  TICKER_ERROR,
  validateQuantity,
} from "@/lib/validation";
import { useLivePortfolio } from "@/hooks/useLivePortfolio";
import { usePortfolio } from "@/providers/PortfolioProvider";
import { usePrices } from "@/providers/PricesProvider";

interface TradeBarProps {
  selectedTicker: string | null;
}

export function TradeBar({ selectedTicker }: TradeBarProps) {
  const { applyPortfolio, refreshHistory } = usePortfolio();
  const { prices } = usePrices();
  const live = useLivePortfolio();

  const [ticker, setTicker] = useState(selectedTicker ?? "");
  const [quantity, setQuantity] = useState("");
  const [pendingSide, setPendingSide] = useState<TradeSide | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (selectedTicker) setTicker(selectedTicker);
  }, [selectedTicker]);

  const normalizedTicker = normalizeTicker(ticker);
  const price = prices[normalizedTicker]?.price ?? null;
  const estimate = useMemo(() => {
    const parsed = Number(quantity);
    if (!Number.isFinite(parsed) || parsed <= 0 || price === null) return null;
    return parsed * price;
  }, [quantity, price]);

  const submit = async (side: TradeSide) => {
    if (pendingSide) return;
    setFeedback(null);
    setError(null);

    const nextTicker = normalizeTicker(ticker);
    if (!isValidTicker(nextTicker)) {
      setError(TICKER_ERROR);
      return;
    }
    const validated = validateQuantity(quantity);
    if (!validated.ok) {
      setError(validated.error);
      return;
    }

    setPendingSide(side);
    try {
      const response = await executeTrade({
        ticker: nextTicker,
        quantity: validated.value,
        side,
      });
      applyPortfolio(response.portfolio);
      void refreshHistory();
      setTicker(nextTicker);
      setQuantity("");
      setFeedback(response.message);
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setPendingSide(null);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submit("buy");
  };

  return (
    <section className="trade-panel" aria-labelledby="trade-title" aria-busy={Boolean(pendingSide)}>
      <div className="panel-header">
        <h2 className="panel-label" id="trade-title">
          Trade
        </h2>
        <span className="panel-meta">Market order</span>
      </div>

      <form className="trade-form" onSubmit={handleSubmit} noValidate>
        <div className="trade-fields">
          <div className="trade-field">
            <label className="field-label" htmlFor="trade-ticker">
              Ticker
            </label>
            <input
              id="trade-ticker"
              data-testid="trade-ticker"
              className="field-input mono"
              value={ticker}
              onChange={(event) => setTicker(event.target.value.toUpperCase())}
              autoComplete="off"
              spellCheck={false}
              maxLength={10}
              disabled={Boolean(pendingSide)}
            />
          </div>

          <div className="trade-field">
            <label className="field-label" htmlFor="trade-quantity">
              Qty
            </label>
            <input
              id="trade-quantity"
              data-testid="trade-quantity"
              className="field-input mono"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              inputMode="decimal"
              autoComplete="off"
              spellCheck={false}
              disabled={Boolean(pendingSide)}
            />
          </div>

          <button
            type="submit"
            className="btn btn-buy"
            data-testid="trade-buy"
            disabled={Boolean(pendingSide)}
          >
            Buy
          </button>
          <button
            type="button"
            className="btn btn-sell"
            data-testid="trade-sell"
            disabled={Boolean(pendingSide)}
            onClick={() => void submit("sell")}
          >
            Sell
          </button>
        </div>

        <div className="trade-hint">
          {price !== null ? (
            <span>
              Last <span className="mono">{formatPrice(price)}</span>
            </span>
          ) : (
            <span>No live price</span>
          )}
          {live ? (
            <span>
              Cash <span className="mono">{formatCurrency(live.cash_balance)}</span>
            </span>
          ) : null}
          {estimate !== null ? (
            <span className="trade-estimate">
              Est. <span className="mono">{formatPrice(estimate)}</span>
            </span>
          ) : null}
        </div>

        <div className="trade-feedback-slot" aria-live="polite">
          {error ? (
            <p className="field-error trade-error" data-testid="trade-error" role="alert">
              {error}
            </p>
          ) : feedback ? (
            <p className="trade-feedback" data-testid="trade-feedback" role="status">
              {feedback}
            </p>
          ) : pendingSide ? (
            <p className="trade-pending" role="status">
              Submitting {pendingSide} order…
            </p>
          ) : null}
        </div>
      </form>
    </section>
  );
}
