/** Shapes frozen in planning/API_CONTRACT.md. */

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number | null;
  timestamp: number;
  source: string;
}

export type PriceMap = Record<string, PriceUpdate>;

export interface WatchlistTicker {
  ticker: string;
  price: number | null;
  previous_price: number | null;
  change: number | null;
  change_pct: number | null;
  open_price: number | null;
  timestamp: number | null;
}

export interface WatchlistResponse {
  tickers: WatchlistTicker[];
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  weight: number;
}

export interface Portfolio {
  cash_balance: number;
  positions_value: number;
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  unrealized_pnl: number;
  positions: Position[];
}

export type TradeSide = "buy" | "sell";

export interface TradeRequest {
  ticker: string;
  quantity: number;
  side: TradeSide;
}

export interface Trade {
  id: string;
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number;
  executed_at: string;
}

export interface TradeResponse {
  message: string;
  trade: Trade;
  portfolio: Portfolio;
}

export interface PortfolioHistoryResponse {
  points: Array<{ total_value: number; recorded_at: string }>;
}

export type HistoryPoint = { totalValue: number; recordedAt: string };

export type ActionStatus = "executed" | "failed";

export interface ChatTradeAction {
  ticker: string;
  side: TradeSide;
  quantity: number;
  status: ActionStatus;
  price?: number | null;
  error?: string | null;
}

export interface ChatWatchlistAction {
  ticker: string;
  action: "add" | "remove";
  status: ActionStatus;
  error?: string | null;
}

export interface ChatActions {
  trades: ChatTradeAction[];
  watchlist_changes: ChatWatchlistAction[];
}

export interface ChatResponse {
  message: string;
  actions: ChatActions;
  portfolio: Portfolio;
}

export type ConnectionState = "connected" | "reconnecting" | "disconnected";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  actions?: ChatActions | null;
  createdAt?: number;
}
