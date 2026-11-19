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
import { appendSample } from "@/lib/series";
import type { ConnectionState, PriceMap, PriceUpdate } from "@/lib/types";

const SSE_URL = "/api/stream/prices";
const DISCONNECT_AFTER_MS = 10_000;

export interface PricesContextValue {
  prices: PriceMap;
  history: Record<string, number[]>;
  /** Unix seconds aligned index-for-index with `history`. */
  historyTimes: Record<string, number[]>;
  connection: ConnectionState;
  lastUpdatedAt: number | null;
}

const PricesContext = createContext<PricesContextValue | null>(null);

export function parsePriceFrame(raw: string): PriceMap | null {
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;

  const frame: PriceMap = {};
  for (const [ticker, value] of Object.entries(payload as Record<string, unknown>)) {
    if (!value || typeof value !== "object" || Array.isArray(value)) continue;
    const record = value as Record<string, unknown>;
    if (typeof record.price !== "number" || !Number.isFinite(record.price)) continue;
    const previous =
      typeof record.previous_price === "number" && Number.isFinite(record.previous_price)
        ? record.previous_price
        : null;
    const update: PriceUpdate = {
      ticker: typeof record.ticker === "string" && record.ticker ? record.ticker : ticker,
      price: record.price,
      previous_price: previous,
      timestamp:
        typeof record.timestamp === "number" && Number.isFinite(record.timestamp)
          ? record.timestamp
          : Date.now() / 1000,
      source: typeof record.source === "string" ? record.source : "stream",
    };
    frame[ticker.toUpperCase()] = update;
  }

  return Object.keys(frame).length > 0 ? frame : null;
}

export function PricesProvider({ children }: { children: ReactNode }) {
  const [prices, setPrices] = useState<PriceMap>({});
  const [history, setHistory] = useState<Record<string, number[]>>({});
  const [historyTimes, setHistoryTimes] = useState<Record<string, number[]>>({});
  const [connection, setConnection] = useState<ConnectionState>("reconnecting");
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const statusRef = useRef<ConnectionState>("reconnecting");
  const lastContactRef = useRef<number | null>(null);

  const setStatus = useCallback((next: ConnectionState) => {
    if (statusRef.current === next) return;
    statusRef.current = next;
    setConnection(next);
  }, []);

  useEffect(() => {
    lastContactRef.current = Date.now();

    if (typeof EventSource === "undefined") {
      setStatus("disconnected");
      return;
    }

    let source: EventSource | null = null;
    let disposed = false;

    try {
      source = new EventSource(SSE_URL);
    } catch {
      setStatus("disconnected");
      return;
    }

    source.onopen = () => {
      if (disposed) return;
      lastContactRef.current = Date.now();
      setStatus("connected");
    };

    source.onmessage = (event: MessageEvent<string>) => {
      if (disposed) return;
      lastContactRef.current = Date.now();
      const frame = parsePriceFrame(event.data);
      if (!frame) return;

      setPrices(frame);
      setHistory((previous) => {
        const next: Record<string, number[]> = { ...previous };
        for (const [ticker, update] of Object.entries(frame)) {
          next[ticker] = appendSample(previous[ticker], update.price);
        }
        return next;
      });
      setHistoryTimes((previous) => {
        const next: Record<string, number[]> = { ...previous };
        for (const [ticker, update] of Object.entries(frame)) {
          next[ticker] = appendSample(previous[ticker], update.timestamp);
        }
        return next;
      });
      setLastUpdatedAt(Date.now());
      setStatus("connected");
    };

    source.onerror = () => {
      if (disposed) return;
      setStatus("reconnecting");
    };

    // A browser retry can stay silent; the contract wants an explicit offline
    // state after ten seconds without a frame.
    const watchdog = window.setInterval(() => {
      if (disposed) return;
      const lastContact = lastContactRef.current;
      if (lastContact !== null && Date.now() - lastContact >= DISCONNECT_AFTER_MS) {
        setStatus("disconnected");
      }
    }, 1_000);

    return () => {
      disposed = true;
      window.clearInterval(watchdog);
      source?.close();
    };
  }, [setStatus]);

  const value = useMemo<PricesContextValue>(
    () => ({ prices, history, historyTimes, connection, lastUpdatedAt }),
    [prices, history, historyTimes, connection, lastUpdatedAt],
  );

  return <PricesContext.Provider value={value}>{children}</PricesContext.Provider>;
}

export function usePrices(): PricesContextValue {
  const context = useContext(PricesContext);
  if (!context) throw new Error("usePrices must be used inside PricesProvider");
  return context;
}
