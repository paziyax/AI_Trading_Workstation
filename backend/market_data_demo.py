"""Live terminal demo of the market data layer.

Run from the ``backend`` directory::

    uv run market_data_demo.py
    uv run market_data_demo.py --tickers AAPL,TSLA,NVDA --history 120 --sort ticker

The demo is a **read-only consumer** of :class:`~app.market.cache.PriceCache`: it never writes
prices, so it cannot corrupt ``change`` values. Sparkline history is accumulated here — one sample
per cache version change — which is exactly what the browser client will do over SSE.

The source defaults to the simulator so the demo always shows live movement. ``--source auto``
follows ``.env`` (which ``uv run`` loads automatically) and uses Massive when a key is present;
``--source massive`` forces it.

``--interval`` only affects the simulator. It does **not** rescale ``GBMSimulator.dt``, so values
other than 0.5 s change the perceived volatility rather than just the speed.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from rich import box
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.table import Table
from rich.text import Text

from app.market.cache import PriceCache
from app.market.config import ConfigurationError, MarketDataConfig
from app.market.factory import create_market_data_source
from app.market.interface import MarketDataSource
from app.market.models import PriceUpdate
from app.market.seed_prices import SEED_PRICES
from app.market.simulator import SimulatorDataSource

UNICODE_RAMP = "▁▂▃▄▅▆▇█"
ASCII_RAMP = ".:-=+*#%@"

FLASH_SECONDS = 0.35
PLACEHOLDER = "—"
MIN_TREND_WIDTH = 8
TREND_RESERVED = 47  # columns taken by ticker, price, change, percent, padding

ACCENT_BLUE = "#209dd7"
ACCENT_YELLOW = "#ecad0a"

BADGES: dict[str, tuple[str, str]] = {
    "simulator": ("SIM", ACCENT_BLUE),
    "snapshot": ("LIVE", "green"),
    "eod": ("EOD", ACCENT_YELLOW),
}


def signed(value: float, digits: int = 2) -> str:
    """``+1.25`` / ``-1.25``, but never ``-0.00``."""
    if abs(value) < 0.5 * 10**-digits:
        return f"{0:.{digits}f}"
    return f"{value:+,.{digits}f}"


# --------------------------------------------------------------------------- sparkline


class Sparkline:
    """Rolling window of prices rendered as a block-character trend line."""

    def __init__(self, width: int, glyphs: str = UNICODE_RAMP) -> None:
        self._samples: deque[float] = deque(maxlen=max(2, width))
        self._glyphs = glyphs

    def add(self, price: float) -> None:
        self._samples.append(price)

    def __len__(self) -> int:
        return len(self._samples)

    @property
    def first(self) -> float | None:
        return self._samples[0] if self._samples else None

    @property
    def last(self) -> float | None:
        return self._samples[-1] if self._samples else None

    def trend(self) -> Literal["up", "down", "flat"]:
        if len(self._samples) < 2:
            return "flat"
        first, last = self._samples[0], self._samples[-1]
        if last > first:
            return "up"
        if last < first:
            return "down"
        return "flat"

    def render(self) -> str:
        count = len(self._samples)
        if count == 0:
            return PLACEHOLDER
        if count == 1:
            return self._glyphs[0]

        low, high = min(self._samples), max(self._samples)
        span = high - low
        top = len(self._glyphs) - 1
        if span <= 0:
            return self._glyphs[top // 2] * count
        return "".join(self._glyphs[round((price - low) / span * top)] for price in self._samples)


# --------------------------------------------------------------------------- row state


@dataclass
class Row:
    """Everything the table needs about one ticker."""

    ticker: str
    spark: Sparkline
    first_price: float | None = None
    last_price: float | None = None
    previous_price: float | None = None
    direction: str = "flat"
    flash_until: float = field(default=0.0)

    def observe(self, update: PriceUpdate, now: float, *, flash: bool) -> None:
        self.spark.add(update.price)
        if self.first_price is None:
            self.first_price = update.price
        self.previous_price = update.previous_price
        self.last_price = update.price
        self.direction = update.direction
        if flash and update.direction != "flat":
            self.flash_until = now + FLASH_SECONDS

    @property
    def change(self) -> float | None:
        if self.first_price is None or self.last_price is None:
            return None
        return round(self.last_price - self.first_price, 2)

    @property
    def change_percent(self) -> float | None:
        if not self.first_price or self.last_price is None:
            return None
        return (self.last_price - self.first_price) / self.first_price * 100.0


# --------------------------------------------------------------------------- demo


class MarketDemo:
    """Polls the cache and paints a live table."""

    def __init__(
        self,
        cache: PriceCache,
        source: MarketDataSource,
        console: Console,
        *,
        history: int = 60,
        refresh: float = 10.0,
        sort: str = "change",
        ascii_glyphs: bool = False,
        flash: bool = True,
        writer: "csv._writer | None" = None,
    ) -> None:
        self._cache = cache
        self._source = source
        self._console = console
        self._refresh = refresh
        self._sort = sort
        self._flash = flash
        self._writer = writer
        self._glyphs = ASCII_RAMP if ascii_glyphs else UNICODE_RAMP
        self._width = max(MIN_TREND_WIDTH, min(history, console.width - TREND_RESERVED))
        self._rows: dict[str, Row] = {}
        self._last_version = -1

    # -- data -------------------------------------------------------------
    def sample(self) -> bool:
        """Take one frame from the cache. Returns True when something changed."""
        version = self._cache.version
        if version == self._last_version:
            return False
        self._last_version = version

        now = datetime.now().timestamp()
        for ticker, update in self._cache.snapshot().items():
            row = self._rows.get(ticker)
            if row is None:
                row = self._rows[ticker] = Row(ticker, Sparkline(self._width, self._glyphs))
            row.observe(update, now, flash=self._flash)
            if self._writer is not None:
                self._writer.writerow(
                    [
                        datetime.now().isoformat(timespec="milliseconds"),
                        ticker,
                        f"{update.price:.2f}",
                        f"{update.previous_price:.2f}",
                        f"{update.change:+.2f}",
                        f"{update.change_percent:+.4f}",
                        update.direction,
                        update.source,
                    ]
                )
        return True

    # -- rendering --------------------------------------------------------
    def render(self) -> RenderableType:
        return Group(self._header(), self._table(), self._footer())

    def _header(self) -> Text:
        health = self._source.health()
        badge, colour = BADGES.get(health.mode, (health.mode.upper(), "white"))
        if health.connected:
            dot, dot_style = "●", "green"
        elif health.consecutive_failures:
            dot, dot_style = "●", "red"
        else:
            dot, dot_style = "●", "yellow"

        up, down, flat = self._breadth()
        line = Text()
        line.append(" FinAlly ", style="bold white")
        line.append("· market data demo ", style="dim")
        line.append(f" {badge} ", style=f"bold black on {colour}")
        line.append("  ")
        line.append(dot, style=dot_style)
        detail = (health.detail or "ok")[:40]
        line.append(f" {detail}", style="dim")
        line.append("   ")
        line.append(f"▲{up} ", style="green")
        line.append(f"▼{down} ", style="red")
        line.append(f"─{flat}", style="dim")
        line.append(f"   {datetime.now():%H:%M:%S}", style="dim")
        return line

    def _table(self) -> Table:
        table = Table(
            box=box.SIMPLE_HEAD,
            pad_edge=False,
            show_edge=False,
            padding=(0, 1),
        )
        table.add_column("TICKER", style="bold cyan", no_wrap=True, width=8)
        table.add_column("LAST", justify="right", no_wrap=True, width=10)
        table.add_column("CHG", justify="right", no_wrap=True, width=10)
        table.add_column("CHG%", justify="right", no_wrap=True, width=9)
        table.add_column("TREND (session)", no_wrap=True, min_width=self._width)

        rows = self._ordered_rows()
        if not rows:
            table.add_row(
                PLACEHOLDER, PLACEHOLDER, PLACEHOLDER, PLACEHOLDER, "waiting for first tick…"
            )
            return table

        now = datetime.now().timestamp()
        for row in rows:
            change, percent = row.change, row.change_percent
            if change is None:
                style = "dim"
                change_text = percent_text = PLACEHOLDER
            else:
                rounded = round(change, 2)
                style = "green" if rounded > 0 else "red" if rounded < 0 else "dim"
                change_text = signed(rounded)
                percent_text = f"{signed(percent)}%" if percent is not None else PLACEHOLDER

            price_text = Text(
                PLACEHOLDER if row.last_price is None else f"{row.last_price:,.2f}",
                justify="right",
            )
            if now < row.flash_until:
                price_text.stylize(
                    f"bold white on {'dark_green' if row.direction == 'up' else 'dark_red'}"
                )

            trend_style = {"up": "green", "down": "red", "flat": "dim"}[row.spark.trend()]
            table.add_row(
                row.ticker,
                price_text,
                Text(change_text, style=style, justify="right"),
                Text(percent_text, style=style, justify="right"),
                Text(row.spark.render(), style=trend_style, no_wrap=True),
            )
        return table

    def _footer(self) -> Text:
        health = self._source.health()
        parts = [
            f"{len(self._rows)} tickers",
            f"{self._refresh:g} Hz",
            health.mode,
        ]
        if health.age_seconds is not None:
            parts.append(f"last update {health.age_seconds:.1f}s ago")
        if health.last_error:
            parts.append(f"error: {health.last_error[:40]}")
        parts.append("Ctrl+C to quit")

        line = Text(" " + " · ".join(parts), style="dim")
        if health.last_error:
            line.stylize("yellow")
        return line

    # -- helpers ----------------------------------------------------------
    def _breadth(self) -> tuple[int, int, int]:
        up = sum(1 for row in self._rows.values() if row.direction == "up")
        down = sum(1 for row in self._rows.values() if row.direction == "down")
        return up, down, len(self._rows) - up - down

    def _ordered_rows(self) -> list[Row]:
        if self._sort == "ticker":
            return sorted(self._rows.values(), key=lambda row: row.ticker)

        def key(row: Row) -> tuple[float, str]:
            percent = row.change_percent
            return (-(percent if percent is not None else float("-inf")), row.ticker)

        return sorted(self._rows.values(), key=key)


# --------------------------------------------------------------------------- wiring


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live terminal demo of the FinAlly market data layer."
    )
    parser.add_argument(
        "--tickers",
        default="",
        help="comma-separated watchlist (default: the ten seed tickers)",
    )
    parser.add_argument("--history", type=int, default=60, help="sparkline samples to keep (60)")
    parser.add_argument("--interval", type=float, default=0.5, help="simulator tick seconds (0.5)")
    parser.add_argument("--refresh", type=float, default=10.0, help="screen repaints/sec (10)")
    parser.add_argument(
        "--source",
        choices=("auto", "simulator", "massive"),
        default="simulator",
        help="price source; auto follows .env (simulator)",
    )
    parser.add_argument(
        "--sort", choices=("change", "ticker"), default="change", help="row ordering (change)"
    )
    parser.add_argument("--ascii", action="store_true", help="ASCII sparkline glyphs")
    parser.add_argument("--no-flash", action="store_true", help="disable the price flash")
    parser.add_argument("--csv", type=Path, default=None, help="record samples to this CSV file")

    args = parser.parse_args(argv)
    if args.history < 2:
        parser.error("--history must be at least 2")
    if args.interval <= 0:
        parser.error("--interval must be positive")
    if args.refresh <= 0:
        parser.error("--refresh must be positive")
    args.tickers = _parse_tickers(args.tickers)
    return args


def _parse_tickers(raw: str) -> list[str]:
    seen: dict[str, None] = {}
    for token in raw.split(","):
        ticker = token.strip().upper()
        if ticker:
            seen.setdefault(ticker, None)
    return list(seen)


def build_source(
    cache: PriceCache, config: MarketDataConfig, args: argparse.Namespace
) -> MarketDataSource:
    """Simulator when configured, otherwise the real factory (Massive)."""
    simulator_selected = config.source == "simulator" or (
        config.source == "auto" and not config.api_key
    )
    if simulator_selected:
        return SimulatorDataSource(cache, config, interval=args.interval)
    return create_market_data_source(cache, config)


async def run(args: argparse.Namespace, console: Console) -> int:
    try:
        config = replace(MarketDataConfig.from_env(), source=args.source)
    except ConfigurationError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        return 2

    cache = PriceCache()
    try:
        source = build_source(cache, config, args)
    except ConfigurationError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        return 2
    tickers = args.tickers or list(SEED_PRICES)

    handle = None
    writer = None
    if args.csv is not None:
        handle = args.csv.open("w", newline="", encoding="utf-8")
        writer = csv.writer(handle)
        writer.writerow(
            [
                "recorded_at",
                "ticker",
                "price",
                "previous_price",
                "change",
                "change_percent",
                "direction",
                "source",
            ]
        )

    demo = MarketDemo(
        cache,
        source,
        console,
        history=args.history,
        refresh=args.refresh,
        sort=args.sort,
        ascii_glyphs=args.ascii,
        flash=not args.no_flash,
        writer=writer,
    )

    try:
        await source.start(tickers)
    except Exception as exc:  # noqa: BLE001 - a bad key should explain itself, not traceback
        console.print(f"[red]Could not start {source.name}:[/red] {exc}")
        if handle is not None:
            handle.close()
        return 1

    try:
        with Live(
            demo.render(),
            console=console,
            refresh_per_second=args.refresh,
            screen=False,
        ) as live:
            while True:
                demo.sample()
                live.update(demo.render())
                await asyncio.sleep(1.0 / args.refresh)
    finally:
        await source.stop()
        if handle is not None:
            handle.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    console = Console()
    try:
        return asyncio.run(run(args, console))
    except KeyboardInterrupt:
        return 0
    finally:
        console.show_cursor(True)


if __name__ == "__main__":
    sys.exit(main())
