# UI Contract — FinAlly

Frozen between the frontend engineer and the integration tester. Visual rules live in
`DESIGN.md`; data shapes live in `API_CONTRACT.md`. This file defines behaviour and test hooks.

## Layout acceptance

- Desktop 1440×900: header + three columns (watchlist 320, chart/portfolio flexible,
  chat 360). No page-level scrollbar; panels scroll internally.
- 1024×900: chat collapses to a toggleable drawer; watchlist 280; nothing clipped.
- 390×844: single column with tab bar (Watchlist / Chart / Portfolio / Chat); usable.
- Zero console errors on load with the backend running.

## Required `data-testid` hooks

The E2E suite depends on these exact values. They must exist on the real elements.

**Header**

| testid | Element |
| --- | --- |
| `header-total-value` | total portfolio value text (`$10,000.00`) |
| `header-cash` | cash balance text |
| `header-pnl` | signed total P&L text |
| `connection-status` | dot wrapper; also `data-state="connected\|reconnecting\|disconnected"` |

**Watchlist**

| testid | Element |
| --- | --- |
| `watchlist-panel` | panel root |
| `watchlist-row-{TICKER}` | row root (clickable, selects ticker) |
| `watchlist-price-{TICKER}` | price cell |
| `watchlist-change-{TICKER}` | change % cell |
| `watchlist-sparkline-{TICKER}` | sparkline svg |
| `add-ticker-input` / `add-ticker-submit` | add form |
| `remove-ticker-{TICKER}` | remove button (visible on row hover/focus, reachable by keyboard) |

**Chart & portfolio**

| testid | Element |
| --- | --- |
| `main-chart` | chart container for the selected ticker |
| `chart-title` | selected ticker label |
| `trade-ticker` / `trade-quantity` / `trade-buy` / `trade-sell` | trade bar |
| `trade-error` | inline error text when a trade is rejected |
| `trade-feedback` | success message |
| `portfolio-heatmap` | heatmap container |
| `pnl-chart` | portfolio history chart |
| `positions-table` | table root |
| `position-row-{TICKER}` | row |
| `portfolio-panel` | panel root |

**Chat**

| testid | Element |
| --- | --- |
| `chat-panel` | panel root |
| `chat-input` / `chat-send` | composer |
| `chat-message-user` / `chat-message-assistant` | message bubbles (repeated) |
| `chat-loading` | visible only while waiting |
| `chat-actions` | container for executed trade/watchlist chips |
| `chat-error` | failure banner |

## Behaviour acceptance

1. **SSE**: one `EventSource('/api/stream/prices')`. On `open` → dot `connected`; on
   `error` → `reconnecting`, browser retries automatically; after 10 s without a message →
   `disconnected`. Never create more than one EventSource per page.
2. **Flash**: when a ticker's price changes, its price cell gets `data-flash="up"` or
   `"down"` for 500 ms, then returns to `"none"`. Flash must not re-trigger when a frame
   repeats the same price.
3. **Sparkline**: keeps the last 90 samples per ticker from page load; renders nothing
   (reserved space) until 2 samples exist. No random data ever.
4. **Selection**: clicking a watchlist row sets it as the main chart ticker; selected row has
   `aria-selected="true"`. Initial selection is the first watchlist ticker.
5. **Trade**: submit is disabled while the request is in flight. Success clears quantity,
   shows `trade-feedback`, updates header/positions/history immediately. Failure shows the
   backend `detail` in `trade-error` and keeps the form values.
6. **Watchlist**: add validates `^[A-Za-z][A-Za-z0-9.\-]{0,9}$` client-side, uppercases,
   shows the API error on 409. Remove asks for no confirmation (single click) and updates the
   list on 200.
7. **Chat**: sending appends the user bubble, disables input, shows `chat-loading`, then
   appends the assistant bubble plus one chip per action (`Bought 5 AAPL`, `Added PYPL`,
   and red `Failed: ...` chips). Input re-enables on completion; failures show `chat-error`.
8. **Empty states**: no positions → heatmap and table show a one-line empty message with a
   pointer to the trade bar; no chat history → one short greeting from FinAlly.
9. **Currency**: `$` with thousands separators and 2 decimals; percentages signed with
   `+`/`−`; quantities ≤ 4 decimals.
10. **No mock/placeholder data in production code** — only real API/SSE data.
