# FinAlly Frontend

The trading-workstation client for **FinAlly** — a dark, data-dense simulated
portfolio terminal with a live market stream and a portfolio-aware AI assistant.

Next.js 15 App Router, React 19, TypeScript strict, Tailwind CSS v4, Recharts.
The app is a static export (`output: "export"`) served by the FastAPI container
at the same origin as `/api/*`; there are no route handlers, server actions or
middleware, and no environment variables are required by the frontend.

## Commands

```bash
npm install
npm run dev            # http://localhost:3000, expects the API on the same origin
npm run build          # static export into ./out (index.html included)
npm run test -- --run  # Vitest + React Testing Library, no network
npm run typecheck      # tsc --noEmit
npm run start          # serve ./out locally through npx serve
```

For a same-origin dev server, run the FastAPI backend and point it at `out/`, or
reverse-proxy `/api` to port 8000. The production image builds this package and
copies `out/` into the FastAPI `STATIC_DIR`.

## Architecture

```
src/app/                 layout, page, design tokens and all component CSS
src/components/          Header, WatchlistPanel, MainChart, TradeBar,
                         PortfolioPanel (heatmap + P&L + positions), ChatPanel,
                         TerminalShell, small primitives
src/providers/           PricesProvider, PortfolioProvider, WatchlistProvider,
                         ChatProvider
src/hooks/               usePriceFlash, useElementSize, useLivePortfolio
src/lib/                 typed API client, formatting, validation, sparkline and
                         heatmap models, chat action copy
src/test/                mocked EventSource and API fixtures
```

Data flow:

- **PricesProvider** owns the single `EventSource('/api/stream/prices')`, replaces
  the price map on every frame, keeps 90 samples (and matching timestamps) per
  ticker, and maps open/error/silence to `connected`, `reconnecting` or
  `disconnected` after 10 seconds without a frame.
- **PortfolioProvider** fetches `/api/portfolio` on mount, polls every 10 seconds,
  and fetches `/api/portfolio/history` on mount and after trades. Trade and chat
  responses are applied immediately and invalidate stale in-flight polls.
- **WatchlistProvider** owns add/remove with client-side ticker validation and
  surfaces the backend `detail` (including 409s) beside the form.
- **ChatProvider** keeps the local conversation and posts complete messages to
  `/api/chat`; the panel renders action chips and refreshes portfolio, history
  and watchlist after the reply.
- `useLivePortfolio` overlays SSE marks onto the REST snapshot so the header,
  positions table and heatmap move on every tick without extra requests.

Every required `data-testid` hook from `planning/UI_CONTRACT.md` is on the real
element; test selectors do not depend on styling classes.

## Formatting and states

- Currency `$10,000.00`, percentages signed `+1.24% / −1.24%`, quantities up to
  four decimals, local `HH:mm:ss` timestamps.
- Every data surface has loading, empty and error states. Recharts charts use a
  measured container and render nothing at zero size (hidden mobile tabs cannot
  produce chart warnings).
- Price cells flash green/red for 500 ms via `data-flash`; identical repeated
  prices do not restart the flash. Sparklines reserve space but draw no path
  until two real samples exist.
- Keyboard: watchlist rows are focusable options with `aria-selected`, the
  remove control is reachable and visible on focus, focus rings are never
  removed, and the tablet drawer closes with Escape and returns focus to its
  trigger.
- `prefers-reduced-motion` disables flashes, pulses and transitions while keeping
  the colour/state changes.

## Tests

Vitest runs in jsdom with a mocked `fetch` and a double for `EventSource`; no
test reaches the network. Coverage includes formatting, flash timing and
non-retrigger, the 90-sample cap, sparkline reservation, watchlist validation,
409 rendering and error states, removal, trade success/failure/pending, live
portfolio math, heatmap weights and tones, positions rows and empty state, chat
loading and action chips, chat failure, connection state mapping and a full-shell
`data-testid` contract check.

## Layout

- `≥1280px`: header + 320px watchlist / flexible chart + portfolio / 360px chat.
- `768–1279px`: 280px watchlist, chat becomes a drawer opened from the header.
- `<768px`: single column with Watchlist / Chart / Portfolio / Chat tabs; the
  portfolio heatmap and equity chart stack vertically.

Known limits: charts and sparklines are session-only — the API exposes portfolio
snapshots but no historical OHLC endpoint, so price history starts at page load.
