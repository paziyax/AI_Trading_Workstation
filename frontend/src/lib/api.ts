import type {
  ChatResponse,
  HistoryPoint,
  Portfolio,
  PortfolioHistoryResponse,
  TradeRequest,
  TradeResponse,
  WatchlistResponse,
} from "./types";

/** Every request is same-origin and relative, so the FastAPI container serves both. */
const JSON_HEADERS = { Accept: "application/json" } as const;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** FastAPI can send `detail` as a string (domain) or an array (422 validation). */
export function extractDetail(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  const { detail } = payload;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (isRecord(item) && typeof item.msg === "string") return item.msg;
        return null;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length > 0) return messages.join(". ");
  }
  return null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      cache: "no-store",
      headers: {
        ...JSON_HEADERS,
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("Cannot reach the FinAlly server. Check it is running and retry.", 0);
  }

  let payload: unknown = null;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    payload = await response.json().catch(() => null);
  } else {
    const text = await response.text().catch(() => "");
    payload = text ? { detail: text } : null;
  }

  if (!response.ok) {
    const message =
      extractDetail(payload) ?? `Request failed (${response.status} ${response.statusText}).`;
    throw new ApiError(message, response.status);
  }

  return payload as T;
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message.trim()) return error.message;
  return "Something went wrong. Try again.";
}

export function getPortfolio(): Promise<Portfolio> {
  return request<Portfolio>("/api/portfolio");
}

export function getPortfolioHistory(limit = 500): Promise<PortfolioHistoryResponse> {
  return request<PortfolioHistoryResponse>(
    `/api/portfolio/history?limit=${encodeURIComponent(String(limit))}`,
  );
}

export async function getPortfolioHistoryPoints(limit = 500): Promise<HistoryPoint[]> {
  const data = await getPortfolioHistory(limit);
  return (data.points ?? [])
    .filter(
      (point) =>
        Number.isFinite(point.total_value) && typeof point.recorded_at === "string",
    )
    .map((point) => ({ totalValue: point.total_value, recordedAt: point.recorded_at }));
}

export function executeTrade(body: TradeRequest): Promise<TradeResponse> {
  return request<TradeResponse>("/api/portfolio/trade", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getWatchlist(): Promise<WatchlistResponse> {
  return request<WatchlistResponse>("/api/watchlist");
}

export function addWatchlistTicker(ticker: string): Promise<{ ticker: string; added: boolean }> {
  return request<{ ticker: string; added: boolean }>("/api/watchlist", {
    method: "POST",
    body: JSON.stringify({ ticker }),
  });
}

export function deleteWatchlistTicker(ticker: string): Promise<{ ticker: string; removed: boolean }> {
  return request<{ ticker: string; removed: boolean }>(
    `/api/watchlist/${encodeURIComponent(ticker)}`,
    { method: "DELETE" },
  );
}

export function postChat(message: string): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}
