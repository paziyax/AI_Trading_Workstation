"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  addWatchlistTicker,
  deleteWatchlistTicker,
  getWatchlist,
  toErrorMessage,
} from "@/lib/api";
import type { WatchlistTicker } from "@/lib/types";
import { isValidTicker, normalizeTicker, TICKER_ERROR } from "@/lib/validation";

export interface WatchlistContextValue {
  tickers: WatchlistTicker[];
  loading: boolean;
  error: string | null;
  adding: boolean;
  addError: string | null;
  removeError: string | null;
  removing: ReadonlySet<string>;
  addTicker: (raw: string) => Promise<boolean>;
  removeTicker: (ticker: string) => Promise<void>;
  clearAddError: () => void;
  clearRemoveError: () => void;
  refresh: () => Promise<void>;
}

const WatchlistContext = createContext<WatchlistContextValue | null>(null);

function emptyTicker(ticker: string): WatchlistTicker {
  return {
    ticker,
    price: null,
    previous_price: null,
    change: null,
    change_pct: null,
    open_price: null,
    timestamp: null,
  };
}

export function WatchlistProvider({ children }: { children: ReactNode }) {
  const [tickers, setTickers] = useState<WatchlistTicker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Set<string>>(new Set());

  const seq = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++seq.current;
    try {
      const data = await getWatchlist();
      if (id !== seq.current) return;
      setTickers(data.tickers ?? []);
      setError(null);
    } catch (cause) {
      if (id !== seq.current) return;
      setError(toErrorMessage(cause));
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const addTicker = useCallback(async (raw: string): Promise<boolean> => {
    const ticker = normalizeTicker(raw);
    if (!isValidTicker(ticker)) {
      setAddError(TICKER_ERROR);
      return false;
    }

    setAdding(true);
    setAddError(null);
    try {
      await addWatchlistTicker(ticker);
      seq.current += 1;
      setTickers((current) =>
        current.some((entry) => entry.ticker === ticker)
          ? current
          : [...current, emptyTicker(ticker)],
      );
      return true;
    } catch (cause) {
      setAddError(toErrorMessage(cause));
      return false;
    } finally {
      setAdding(false);
    }
  }, []);

  const removeTicker = useCallback(async (ticker: string) => {
    setRemoving((current) => {
      const next = new Set(current);
      next.add(ticker);
      return next;
    });
    setRemoveError(null);
    try {
      await deleteWatchlistTicker(ticker);
      seq.current += 1;
      setTickers((current) => current.filter((entry) => entry.ticker !== ticker));
    } catch (cause) {
      setRemoveError(toErrorMessage(cause));
    } finally {
      setRemoving((current) => {
        const next = new Set(current);
        next.delete(ticker);
        return next;
      });
    }
  }, []);

  const clearAddError = useCallback(() => setAddError(null), []);
  const clearRemoveError = useCallback(() => setRemoveError(null), []);

  const value = useMemo<WatchlistContextValue>(
    () => ({
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
      clearRemoveError,
      refresh,
    }),
    [
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
      clearRemoveError,
      refresh,
    ],
  );

  return <WatchlistContext.Provider value={value}>{children}</WatchlistContext.Provider>;
}

export function useWatchlist(): WatchlistContextValue {
  const context = useContext(WatchlistContext);
  if (!context) throw new Error("useWatchlist must be used inside WatchlistProvider");
  return context;
}
