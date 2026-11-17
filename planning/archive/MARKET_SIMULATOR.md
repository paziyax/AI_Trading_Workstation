# Market Simulator

FinAlly's zero-dependency price source. It runs whenever `MASSIVE_API_KEY` is unset (or the simulator
is forced), so SSE, valuation, trading and P&L all work offline, in CI, and in demos.

Design premise: it must never crash, never produce negative or absurd prices, look like a real intraday
tape at a glance, and be deterministic enough to test.

## Cheat sheet

| Fact | Value |
|---|---|
| Model | geometric Brownian motion + correlated shocks + jump events |
| Tick | 500 ms → 1 simulated tick = 500 ms of market time |
| `dt` | `0.5 / 5,896,800 ≈ 8.478e-8` (fraction of a trading year) |
| σ | annualized, 0.17–0.50 per ticker |
| Correlation | tech 0.6, finance 0.5, TSLA 0.3, cross-group 0.3 |
| Events | `p = 0.001` per ticker per tick, 2–5% jump, no reversion |
| Price is rounded | 2 dp in `step()` and again in `PriceCache` |

## Model

```
S(t+dt) = S(t) · exp( (μ − σ²/2)·dt + σ·√dt·Z ),   Z ~ N(0, 1)
```

Multiplicative (never negative), scale-invariant (a $12 and a $900 name move comparably in percent),
lognormal (so the % column reads correctly), and cheap — one `exp()` per ticker per tick.

### Time calibration

`dt` is a fraction of a **trading year**, not wall-clock seconds:

```
TRADING_SECONDS_PER_YEAR = 252 days × 6.5 h × 3600 s = 5,896,800 s
DEFAULT_DT               = 0.5 / 5,896,800 ≈ 8.478e-8
```

One 500 ms tick is therefore 500 ms of market time, and the simulation runs 1:1 with a real session:

| Wall clock | Simulated market time | Ticks |
|---|---|---|
| 1 minute | 1 minute | 120 |
| 1 hour | 1 hour | 7,200 |
| 6.5 hours | 1 full session | 46,800 |

Consequences: `σ` is directly comparable to real annualized volatility; a one-hour demo covers only
~15% of a session, so the tape is calm unless events fire (correct, not a bug); and **changing the tick
rate changes the speed of simulated time** — `dt` must be recomputed or volatility silently rescales.

Per-tick and per-horizon standard deviations (`≈ σ · √(horizon / 1 year)`):

| Ticker | σ | Per tick | Per minute | Per hour | Per session |
|---|---|---|---|---|---|
| MSFT | 0.20 | 0.006% | 0.064% | 0.49% | 1.26% |
| AAPL | 0.22 | 0.006% | 0.070% | 0.54% | 1.39% |
| NVDA | 0.40 | 0.012% | 0.128% | 0.99% | 2.52% |
| TSLA | 0.50 | 0.015% | 0.159% | 1.24% | 3.15% |

### Correlated moves

Independent draws make the watchlist flash randomly, which reads as fake. Instead:

```
C      = correlation matrix (unit diagonal)
L      = cholesky(C)                  # C = L Lᵀ
Z_corr = L · Z_indep                  # Z_indep ~ N(0, I)
```

`Z_corr` has covariance `C`, so same-sector names move together and the tape gets a "market mood"
without an explicit market factor.

| Pair | ρ |
|---|---|
| tech ↔ tech (`AAPL GOOGL MSFT AMZN META NVDA NFLX`) | `INTRA_TECH_CORR = 0.6` |
| finance ↔ finance (`JPM`, `V`) | `INTRA_FINANCE_CORR = 0.5` |
| TSLA ↔ anything (checked first) | `TSLA_CORR = 0.3` |
| everything else / unknown tickers | `CROSS_GROUP_CORR = 0.3` |

Watchlist edits rebuild the Cholesky factor — `O(n²)` to build, `O(n³)` to decompose. Fine below ~50
tickers; never call it per tick. These constants are positive definite by construction, but *arbitrary*
correlations can break that (see Safety). `n ≤ 1` short-circuits to independent draws.

### Events

```python
if random.random() < event_probability:                 # default 0.001
    magnitude = random.uniform(0.02, 0.05)              # 2–5 %
    sign      = random.choice([-1, 1])
    price *= 1 + magnitude * sign
```

One event per ticker per 1,000 ticks ≈ 8.3 minutes; with ten tickers something fires roughly every
50 s. Shocks are single-tick and never revert, so a run of same-sign events can drift a price 20%+ —
intentional (it looks like a news day), but bound it for long-running tests.

## Seed data

`backend/app/market/seed_prices.py` holds constants only, no logic. Prices are illustrative
magnitudes, not current quotes.

| Ticker | Seed | σ | μ |
|---|---|---|---|
| AAPL | 190 | 0.22 | 0.05 |
| GOOGL | 175 | 0.25 | 0.05 |
| MSFT | 420 | 0.20 | 0.05 |
| AMZN | 185 | 0.28 | 0.05 |
| TSLA | 250 | 0.50 | 0.03 |
| NVDA | 800 | 0.40 | 0.08 |
| META | 500 | 0.30 | 0.05 |
| JPM | 195 | 0.18 | 0.04 |
| V | 280 | 0.17 | 0.04 |
| NFLX | 600 | 0.35 | 0.05 |

Defaults for unknown tickers: σ 0.25, μ 0.05, seed `uniform(50, 300)` at add time (non-deterministic —
seed the RNG for tests). `μ` is irrelevant at these horizons (`0.05 · dt` per tick ≈ 4e-9); it exists so
the model is a proper GBM. New tickers join at their seed price, not at a correlated level, so adding
many names yields many independent walks that merely share a correlation matrix. Refresh the seed
prices periodically or a 2027 demo will look stale.

## Code structure

`GBMSimulator` is pure and synchronous; `SimulatorDataSource` owns everything time-related. That split
is what makes the math unit-testable without an event loop.

```python
class GBMSimulator:
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600      # 5,896,800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR       # ≈ 8.478e-8

    def __init__(self, tickers: list[str], dt: float = DEFAULT_DT,
                 event_probability: float = 0.001) -> None: ...
    def step(self) -> dict[str, float]: ...           # hot path, every 500 ms
    def add_ticker(self, ticker: str) -> None: ...
    def remove_ticker(self, ticker: str) -> None: ...
    def get_price(self, ticker: str) -> float | None: ...
    def get_tickers(self) -> list[str]: ...


class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache, update_interval: float = 0.5,
                 event_probability: float = 0.001) -> None: ...
```

`step()`:

```
if no tickers → {}
Z ← standard_normal(n);  if cholesky: Z ← cholesky @ Z
for i, ticker:
    drift     ← (mu − 0.5·sigma²) · dt
    diffusion ← sigma · sqrt(dt) · Z[i]
    price    ← price · exp(drift + diffusion)
    if rand() < event_probability: price ← price · (1 + uniform(0.02, 0.05) · choice(−1, +1))
    out[ticker] ← round(price, 2)
```

`O(n²)` per tick with the matrix multiply, `O(n)` without; at n = 10 and 2 Hz the loop is dominated by
`asyncio.sleep`, not math.

`SimulatorDataSource` behaviour: `start()` builds the simulator, **seeds the cache** so the first SSE
frame and first paint are populated, then spawns `_run_loop`; `add_ticker()` updates simulator *and*
cache immediately (no blank row); `remove_ticker()` removes from both; `stop()` cancels, awaits, and is
idempotent. Every iteration is wrapped in `try/except Exception: logger.exception(...)` so one bad tick
never kills the feed.

## Tuning

| Knob | Default | Effect |
|---|---|---|
| `update_interval` | 0.5 s | feed cadence; changing it invalidates `dt` |
| `dt` | `0.5 / 5_896_800` | simulated time per tick; keep 1:1 with the interval |
| `sigma` | 0.17–0.50 | intraday amplitude, annualized |
| `mu` | 0.03–0.08 | negligible at these horizons |
| `event_probability` | 0.001 | drama dial; 0.005 ≈ an event every 10 s |
| shock range | 2–5% | visual impact of an event |
| correlation | 0.3 / 0.5 / 0.6 | "market mood" coherence |

**Raise `event_probability` before `sigma`.** Sigma changes the texture of the whole tape; events add
punctuation. For calmer screenshots, cut the shock magnitude to 1–2% and keep the frequency.

## Safety

* **Floor the price.** GBM cannot go negative, but a long run of down-shocks can underflow:
  `self._prices[t] = max(self._prices[t], 0.01)`.
* **Guard the Cholesky.** `np.linalg.cholesky` raises `LinAlgError` on a non-PD matrix; the current
  constants are safe, arbitrary future ones are not. Catch it and retry with `1e-8 · I` jitter, or fall
  back to `None`. A degraded uncorrelated simulation beats a 500 on a watchlist edit.
* **Do not round inside the multiplication** — small prices would stall at 0.01. Round at the end.

## Testing

Inject the RNGs (no API break) so `GBMSimulator(tickers, np_rng=default_rng(42), py_rng=Random(42))`
replays byte-identically. Assert: prices stay finite and `> 0` over 10k ticks; `step()` returns exactly
the tracked tickers at 2 dp; `add_ticker` mid-run doesn't perturb others; `remove_ticker` is idempotent;
`start()` seeds the cache before the first tick; `stop()` halts writes and the loop survives a raised
exception; event frequency ≈ `event_probability` over 100k ticks; session σ ≈ `sigma / √252`.

Also sample 5k steps and check Pearson ρ within ±0.1 of target. This is the test people skip — a
transposed `L` still produces plausible prices, so the bug survives for months.

## Sources

* This repository: `backend/app/market/{simulator,seed_prices,cache}.py`,
  `backend/tests/market/test_simulator.py`, `planning/PLAN.md` §6.
* GBM and the `(μ − σ²/2)` drift correction — standard result; e.g. Hull, *Options, Futures, and Other
  Derivatives*.
* Cholesky and `numpy.random.Generator` — <https://numpy.org/doc/stable/reference/generated/numpy.linalg.cholesky.html>,
  <https://numpy.org/doc/stable/reference/random/generator.html> (accessed 18 Nov 2026).
* Plan context that motivates the fallback — `MASSIVE_API.md`.
