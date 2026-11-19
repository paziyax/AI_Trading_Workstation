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
import { getPortfolio, getPortfolioHistoryPoints, toErrorMessage } from "@/lib/api";
import type { HistoryPoint, Portfolio } from "@/lib/types";

const PORTFOLIO_POLL_MS = 10_000;
const HISTORY_POLL_MS = 30_000;

export interface PortfolioContextValue {
  portfolio: Portfolio | null;
  history: HistoryPoint[];
  loading: boolean;
  historyLoading: boolean;
  error: string | null;
  historyError: string | null;
  refresh: () => Promise<void>;
  refreshHistory: () => Promise<void>;
  applyPortfolio: (next: Portfolio) => void;
}

const PortfolioContext = createContext<PortfolioContextValue | null>(null);

export function PortfolioProvider({ children }: { children: ReactNode }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const portfolioSeq = useRef(0);
  const historySeq = useRef(0);

  const refresh = useCallback(async () => {
    const seq = ++portfolioSeq.current;
    try {
      const next = await getPortfolio();
      if (seq !== portfolioSeq.current) return;
      setPortfolio(next);
      setError(null);
    } catch (cause) {
      if (seq !== portfolioSeq.current) return;
      setError(toErrorMessage(cause));
    } finally {
      if (seq === portfolioSeq.current) setLoading(false);
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    const seq = ++historySeq.current;
    try {
      const points = await getPortfolioHistoryPoints(500);
      if (seq !== historySeq.current) return;
      setHistory(points);
      setHistoryError(null);
    } catch (cause) {
      if (seq !== historySeq.current) return;
      setHistoryError(toErrorMessage(cause));
    } finally {
      if (seq === historySeq.current) setHistoryLoading(false);
    }
  }, []);

  const applyPortfolio = useCallback((next: Portfolio) => {
    // Invalidate in-flight polls so a stale snapshot cannot overwrite a trade.
    portfolioSeq.current += 1;
    setPortfolio(next);
    setError(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
    void refreshHistory();

    const portfolioTimer = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      void refresh();
    }, PORTFOLIO_POLL_MS);

    const historyTimer = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      void refreshHistory();
    }, HISTORY_POLL_MS);

    return () => {
      window.clearInterval(portfolioTimer);
      window.clearInterval(historyTimer);
    };
  }, [refresh, refreshHistory]);

  const value = useMemo<PortfolioContextValue>(
    () => ({
      portfolio,
      history,
      loading,
      historyLoading,
      error,
      historyError,
      refresh,
      refreshHistory,
      applyPortfolio,
    }),
    [
      portfolio,
      history,
      loading,
      historyLoading,
      error,
      historyError,
      refresh,
      refreshHistory,
      applyPortfolio,
    ],
  );

  return <PortfolioContext.Provider value={value}>{children}</PortfolioContext.Provider>;
}

export function usePortfolio(): PortfolioContextValue {
  const context = useContext(PortfolioContext);
  if (!context) throw new Error("usePortfolio must be used inside PortfolioProvider");
  return context;
}
