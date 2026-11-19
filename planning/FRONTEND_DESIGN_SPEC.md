# FinAlly — Frontend Design Spec

**Design read:** A single-page trading workstation for a retail trader evaluating a
simulated portfolio; a "quiet terminal" language — flat panels, hairlines, tabular
numbers, one yellow brand accent — leaning on the brand `DESIGN.md`.

**Dials:** variance 2/10 · motion 2/10 · density 9/10.

## Direction

Bloomberg-terminal bones with modern restraint. Structure comes from a strict
three-column grid and tonal surfaces, not cards, gradients or shadows. Purple is
reserved for order submission; blue is information and focus; green/red only carry
market direction and are always paired with signs and text.

## Tokens

All values come from `DESIGN.md` (section 2 and 3) through CSS variables in
`src/app/globals.css`. One deliberate addition: `--text-label: #8b98aa` is used for
11 px uppercase labels because the brand `--text-muted` (#6b7789) measures 3.85:1
on the panel surface, below the 4.5:1 floor. `--text-muted` remains a token for
non-text use.

## Type

- UI/display: Inter Variable.
- Numbers, tickers, prices, percentages, timestamps: JetBrains Mono Variable with
  tabular figures.
- Closed scale: 11 / 12 / 13 / 14 / 16 / 18 / 20 / 22 px. Uppercase labels get
  0.05–0.06em tracking; prices 18–22 px use −0.01em.
- All text ≥ 11 px.

## Layout

| Viewport | Composition |
| --- | --- |
| 1440×900 | 56 px header; 320 watchlist + trade; flexible chart → allocation/equity → positions; 360 AI |
| 1024×900 | 280 watchlist; chat is a header-triggered overlay drawer with backdrop, Escape and focus return |
| 390×844 | Header stats with compact labels; one panel at a time behind a 52 px tab bar; allocation and equity stack |

The shell is `100dvh` with `overflow:hidden`; every long region scrolls internally.
Watchlist rows are 44 px, table rows 40 px, panel headers 36 px.

## Components and states

- Watchlist: 24 px column header, 44 px rows, session sparkline, signed change,
  yellow selected bar, `<` `>` `×` remove on hover/focus (always visible on touch),
  500 ms `data-flash` on the price cell.
- Chart: measured Recharts AreaChart, right-side price axis, local time axis,
  session tick count and source footer; loading, no-tick, no-selection states.
- Portfolio: custom Treemap sized by market value and tinted by P&L percent with
  direct labels; equity LineChart with $10k baseline; dense positions table with
  signed P&L and %; explicit loading, empty and unavailable states.
- Trade: visible Ticker/Qty labels, purple Buy, outlined red Sell, pending lock,
  inline `detail` error, success feedback, live last/estimate hint.
- Chat: greeting, user/assistant bubbles, action chips (`Bought 5 AAPL`,
  `Added PYPL`, `Failed: …`), skeleton-style loading row, dismissible error,
  Enter-to-send. Drawer variant on tablet.
- Focus: 2 px `--primary` ring with 2 px offset on every focusable element.
  Disabled controls are 40% opacity and not interactive.
- Motion: 120–180 ms ease-out on state; 500 ms flash fade; reduced-motion removes
  animation and fade durations while preserving state colour.

## Content rules

- `$10,000.00`; `+1.24%` / `−1.24%`; quantities ≤ 4 decimals; local `HH:mm:ss`.
- No raw JSON, stack traces or `undefined`; API errors render their plain `detail`.
- Empty copy names the next action ("Use the trade bar to buy your first shares").
- No placeholder prices, fake company data or invented metrics.

## Acceptance

- All `data-testid` hooks in `planning/UI_CONTRACT.md` are present on real elements.
- One EventSource; 90-sample cap; no sparkline before two samples; flash never
  retriggers on an identical price.
- 46 Vitest/RTL tests; `out/index.html` produced by `npm run build`.
- Keyboard pass, contrast measured on the rendered page, no page scroll at
  1440×900, drawer and mobile tabs operable without console errors.
