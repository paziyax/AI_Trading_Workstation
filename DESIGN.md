# FinAlly — Design System

Brand and visual contract for all frontend work. Derived from `planning/PLAN.md` §2.
Any dezign0 skill (`frontend-design`, `critique`, `redesign`, `design-system-extract`)
must treat this file as the source of truth and must not invent a new direction.

## 1. Direction

**"Quiet terminal."** A data-dense professional trading workstation, not a crypto landing page.
Bloomberg-terminal bones with modern restraint: flat panels, hairline borders, tabular numbers,
one accent colour used sparingly. Every pixel must carry information.

Explicitly rejected: gradients as decoration, glassmorphism, glows, oversized hero type,
rounded-pill buttons, illustrations, emoji as UI, stock dashboard templates.

## 2. Colour tokens

```css
:root {
  /* surfaces */
  --bg-base:      #0d1117;  /* page background */
  --bg-panel:     #131a24;  /* cards, panels */
  --bg-elevated:  #1a1a2e;  /* popovers, selected rows, chart background */
  --bg-hover:     #1b2430;  /* row hover */
  --border:       #263041;  /* hairline separators */
  --border-strong:#374151;  /* focused/active panel edges */

  /* text */
  --text-primary:   #e6edf3;
  --text-secondary: #9aa7b8;
  --text-muted:     #6b7789;

  /* brand */
  --accent:   #ecad0a;  /* FinAlly yellow: logo mark, active tab, key figures */
  --primary:  #209dd7;  /* links, focus rings, chart line, info */
  --secondary:#753991;  /* submit buttons, primary CTA */

  /* semantic (market) */
  --positive: #2ea043;  /* uptick, profit */
  --negative: #f85149;  /* downtick, loss */
  --warning:  #d29922;  /* reconnecting, degraded */
  --neutral:  #8b949e;
}
```

Usage rules:

- Yellow is an accent, never a large fill. Max one yellow element per view region.
- Green/red are never the only signal: pair with `+`/`−` and an arrow glyph.
- Price flash: background `rgba(46,160,67,0.18)` up / `rgba(248,81,73,0.18)` down,
  fading to transparent over 500 ms.
- Contrast: body text ≥ 4.5:1 on its surface. Verify with `dezign0_lint`.

## 3. Typography

- UI / display: **Inter Variable** (`@fontsource-variable/inter`).
- Numbers, tickers, prices: **JetBrains Mono Variable** (`@fontsource-variable/jetbrains-mono`),
  `font-variant-numeric: tabular-nums`. All prices, quantities and percentages use it.
- No third family. No text below 11 px.

| Token | Size / line-height | Use |
| --- | --- | --- |
| `text-2xs` | 11 / 14, +0.06em uppercase | panel labels, table headers |
| `text-xs` | 12 / 16 | secondary metadata |
| `text-sm` | 13 / 18 | table body, chat body, inputs |
| `text-base` | 14 / 20 | default UI |
| `text-lg` | 16 / 22 | panel titles |
| `text-xl` | 20 / 26 | portfolio value |
| `text-3xl` | 32 / 36, tabular | hero numbers only |

## 4. Space, shape, depth

- 4 px base scale: 4, 8, 12, 16, 20, 24, 32, 48.
- Radii: 4 (inputs, chips), 6 (panels), 10 (modal only). Nothing fully rounded.
- Borders: 1 px `var(--border)`. Panels are separated by hairlines, not shadows.
- Shadows: only for floating overlays (`0 8px 24px rgba(0,0,0,0.45)`). No shadows on panels.
- Panel header: 36 px tall, label in `text-2xs` uppercase, optional right-aligned control.

## 5. Layout

Desktop-first, single page, three columns inside a 100vh shell:

```
┌──────────────────────────────────────────────────────────────┐
│ header 56px: logo · total value · total P&L · cash · dot     │
├──────────────┬───────────────────────────────┬───────────────┤
│ watchlist    │ main chart                    │ AI assistant  │
│ 320px        │ flexible (min 480px)          │ 360px         │
│ + trade bar  ├───────────────────────────────┤ collapsible   │
│              │ heatmap | P&L chart (stacked)  │               │
│              ├───────────────────────────────┤               │
│              │ positions table                │               │
└──────────────┴───────────────────────────────┴───────────────┘
```

- Breakpoints: `≥1280` full three columns; `768–1279` chat becomes an overlay drawer,
  watchlist 280 px; `<768` stacked single column with tabbed panels (watchlist / chart /
  portfolio / chat). Desktop is the priority; tablet must not break.
- Row heights: watchlist 44 px, tables 40 px. Dense but never cramped: 12 px cell padding.
- Scroll containers get `scrollbar-width: thin` and `overscroll-behavior: contain`.
- The app fills the viewport; the page itself never scrolls (panels scroll internally).

## 6. Component states (all mandatory)

Every interactive element needs default / hover / focus-visible / active / disabled, and every
data surface needs loading / empty / error / stale states.

- **Focus ring**: 2 px `var(--primary)` with 2 px offset. Never removed.
- **Watchlist row**: hover raises background; selected row gets a 2 px left `--accent` bar
  and `--bg-elevated`. Price cell flashes on change.
- **Connection dot**: `--positive` connected, `--warning` reconnecting (pulse 1.2 s),
  `--negative` disconnected; always paired with a text label on hover/focus.
- **Empty states**: one sentence + the action that resolves it (e.g. "No positions yet —
  buy your first shares below"). Never a bare "No data".
- **Loading**: skeleton rows for lists, 40 % opacity chart placeholder. No spinners over 300 ms.
- **Errors**: inline banner at the top of the affected panel, dismissible, with the retry action.
- **Disabled**: 40 % opacity, `cursor: not-allowed`, no hover reaction.

## 7. Motion

- 120–180 ms `ease-out` for hover/focus/expand; 500 ms for price flash fade.
- Nothing loops except the reconnect pulse. No parallax, no entrance animations on load.
- `prefers-reduced-motion: reduce` disables flashes and pulses (keep colour change, drop fade).

## 8. Content rules

- Numbers: prices `$190.42`, quantities up to 4 decimals trimmed, percentages `+1.24%`.
- Negative values use a real minus sign `−`; P&L is always signed.
- Ticker labels are uppercase mono; company names are optional and secondary.
- Timestamps in local time, `HH:mm:ss`; the P&L chart axis shows `HH:mm`.
- Chat copy: concise, data-driven, no exclamation marks, no "As an AI".
- Never show raw JSON, stack traces, or `undefined`. Map failures to plain sentences.

## 9. Verification

- Static: `dezign0_lint` on the built artifact must report no P0/P1 findings.
- Rendered: `dezign0_measure` at 1440×900, 1024×900, 768×900, 390×844 — no clipping, no
  contrast failures, no console errors.
- Manual: keyboard-only pass through header → watchlist → trade bar → chat; visible focus
  at every stop.
