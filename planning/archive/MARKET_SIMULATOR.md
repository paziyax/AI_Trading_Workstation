# Market Simulator — Architecture, Model, and Code Structure

The simulator is FinAlly's zero-dependency market data source. It runs whenever `MASSIVE_API_KEY`
is not configured (or when the simulator is explicitly selected), producing a continuous, plausible
price stream so the entire platform — SSE, portfolio valuation, trading, P&L charts — works offline,
in CI, and in demos.

**Design premise:** the simulator is not a toy. It must (a) never crash, (b) never produce negative
or absurd prices, (c) produce moves that look like a real intraday tape at a glance, and (d) be
deterministic enough to test.

---

## 1. Where it sits

```
SimulatorDataSource          (async adapter: lifecycle, timing, cache writes)
        │
        ▼
GBMSimulator                 (pure math: prices in → prices out, no I/O, no asyncio)
        │
        ├── seed_prices.py   (SEED_PRICES, TICKER_PARAMS, DEFAULT_PARAMS, correlation constants)
        ▼
PriceCache.update(ticker, price)   →  SSE / valuation / trading
```

The split matters:

* **`GBMSimulator` is synchronous and pure.** Given the same RNG state, `step()` is reproducible.
  It can be unit-tested without an event loop, and a `dt`/`event_probability` change is a one-line
  test fixture change.
* **`SimulatorDataSource` owns everything time-related**: the 500 ms loop, `asyncio.create_task`,
  cancellation, cache seeding, and error isolation. It is one of two implementations of
  `MarketDataSource` (see `MARKET_INTERFACE.md`).

---

## 2. Simulation approach

### 2.1 Why Geometric Brownian Motion

GBM is the standard continuous-time model for equity prices:

```
S(t+dt) = S(t) · exp( (μ − σ²/2)·dt + σ·√dt·Z ),   Z ~ N(0, 1)
```

Properties that matter here:

| Property | Why FinAlly cares |
|---|---|
| Multiplicative | Prices can never go negative — `exp()` is strictly positive |
| Scale-invariant | A $12 stock and a $900 stock behave comparably in percentage terms |
| Lognormal | Percentage moves are normal → the "% change" column looks right |
| Standard | `μ`/`σ` are annualized numbers a reader can sanity-check against real tickers |
| Cheap | One `exp()` per ticker per tick; no history buffer required |

Alternatives considered are in §10.

### 2.2 Time calibration — the key detail

`dt` is expressed in **fractions of a trading year**, not wall-clock seconds:

```
TRADING_SECONDS_PER_YEAR = 252 trading days × 6.5 h/day × 3600 s/h = 5,896,800 s
DEFAULT_DT               = 0.5 / 5,896,800 ≈ 8.478 × 10⁻⁸
```

So **one 500 ms tick = 500 ms of market time**, and the simulation runs at 1:1 with a real session:

| Wall clock | Simulated market time | Ticks |
|---|---|---|
| 1 second | 1 second | 2 |
| 1 minute | 1 minute | 120 |
| 1 hour | 1 hour | 7,200 |
| 6.5 hours | 1 full trading day | 46,800 |

Consequences:

* `σ` is directly comparable to real annualized volatility (a 0.22 name behaves like a 22%-vol name).
* A **one-hour demo** only covers ~15% of a session, so the tape feels calm unless events fire.
  This is correct behavior, not a bug — tune `event_probability` for drama instead of inflating `σ`.
* Changing the tick rate changes the *speed of simulated time*. If the loop ever moves off 0.5 s,
  `dt` must be recomputed (or scoped to the loop start time) or volatility will silently rescale.

Per-tick and per-horizon standard deviations for the default parameters:

| Ticker | σ | Per tick (0.5 s) | Per minute | Per hour | Per session |
|---|---|---|---|---|---|
| MSFT | 0.20 | 0.006% | 0.064% | 0.49% | 1.26% |
| AAPL | 0.22 | 0.006% | 0.070% | 0.54% | 1.39% |
| NVDA | 0.40 | 0.012% | 0.128% | 0.99% | 2.52% |
| TSLA | 0.50 | 0.015% | 0.159% | 1.24% | 3.15% |

(`per-horizon ≈ σ · √(horizon / 1 year)`, `1 session = 1/252 year`.)

### 2.3 Correlated moves

Real equities co-move. Independent draws would make the watchlist flash randomly, which reads as
obviously fake. FinAlly therefore draws **correlated** normals:

```
C = correlation matrix (n × n, unit diagonal)
L = cholesky(C)                       # C = L Lᵀ
Z_corr = L · Z_indep                  # Z_indep ~ N(0, I)
```

`Z_corr` has covariance `C`, so same-sector names move together and the tape develops "market
mood" without any explicit market factor.

Correlation structure (`backend/app/market/seed_prices.py`):

| Pair | ρ |
|---|---|
| Tech ↔ tech (`AAPL GOOGL MSFT AMZN META NVDA NFLX`) | `INTRA_TECH_CORR = 0.6` |
| Finance ↔ finance (`JPM`, `V`) | `INTRA_FINANCE_CORR = 0.5` |
| TSLA ↔ anything | `TSLA_CORR = 0.3` (checked first — it does its own thing) |
| Everything else / unknown tickers | `CROSS_GROUP_CORR = 0.3` |

Structural notes:

* Watchlist changes call `_rebuild_cholesky()` — `O(n²)` build plus `O(n³)` decomposition. Fine for
  n < 50; do not call it per tick.
* A matrix built this way (unit diagonal, off-diagonals in {0.3, 0.5, 0.6}) is positive definite, so
  `np.linalg.cholesky` succeeds. **Arbitrary** correlation values can break that — see §7.2.
* Correlation is **static**. There is no regime switching or volatility clustering (see §11).
* `n ≤ 1` short-circuits to `self._cholesky = None` and `step()` uses independent draws.

### 2.4 Random events ("news shocks")

A jump process layered on the diffusion:

```python
if random.random() < event_probability:                 # default 0.001
    magnitude = random.uniform(0.02, 0.05)              # 2–5 %
    sign      = random.choice([-1, 1])
    price *= 1 + magnitude * sign
```

Expected frequency, per ticker, at 2 Hz:

```
P(event per tick) = 0.001  →  one event per 1,000 ticks = 500 s ≈ 8.3 min
```

With the default 10-ticker watchlist an event fires **somewhere** roughly every 50 s — enough to make
the dashboard feel alive without turning it into noise. Each event is a **single-tick** price jump;
there is no post-event mean reversion, so a series of same-sign shocks can drift a price 20%+ over a
long session. That is intentional (it looks like a news day) but should be bounded if the simulator is
used for long-running tests — see §7.3.

---

## 3. Seed data

`backend/app/market/seed_prices.py` — constants only, no logic:

```python
SEED_PRICES = {                        # illustrative starting levels
    "AAPL": 190.00, "GOOGL": 175.00, "MSFT": 420.00, "AMZN": 185.00,
    "TSLA": 250.00, "NVDA": 800.00, "META": 500.00, "JPM": 195.00,
    "V": 280.00, "NFLX": 600.00,
}

TICKER_PARAMS = {                      # annualized mu, sigma
    "AAPL": {"sigma": 0.22, "mu": 0.05}, "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT": {"sigma": 0.20, "mu": 0.05}, "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA": {"sigma": 0.50, "mu": 0.03}, "NVDA":  {"sigma": 0.40, "mu": 0.08},
    "META": {"sigma": 0.30, "mu": 0.05}, "JPM":   {"sigma": 0.18, "mu": 0.04},
    "V":    {"sigma": 0.17, "mu": 0.04}, "NFLX":  {"sigma": 0.35, "mu": 0.05},
}

DEFAULT_PARAMS  = {"sigma": 0.25, "mu": 0.05}
CORRELATION_GROUPS = {"tech": {...}, "finance": {...}}
INTRA_TECH_CORR, INTRA_FINANCE_CORR, CROSS_GROUP_CORR, TSLA_CORR = 0.6, 0.5, 0.3, 0.3
```

Rules and caveats:

* **Prices are illustrative, not current.** They were chosen for realistic *magnitude*, not accuracy.
  A demo will look odd if NVDA trades at $800 in 2027 — refresh this dict periodically, or seed from
  the `MASSIVE_API_KEY` path when available.
* **Unknown tickers** get `random.uniform(50, 300)` at add time. Convenient, but non-deterministic —
  a freshly added ticker can land at $52 or $297. For reproducible tests, seed the RNG (§6).
* **`mu`** is nearly irrelevant at these horizons: `0.05 · dt` per tick is ~4×10⁻⁹. It exists so the
  model is a proper GBM, not to produce trends. Do not tune it expecting drift.
* **New tickers join at their seed price**, not at a correlated level with the rest. Adding 50 names
  makes 50 independent random walks that happen to share a correlation matrix.

---

## 4. Class structure

### 4.1 `GBMSimulator` (`backend/app/market/simulator.py`)

```python
class GBMSimulator:
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600      # 5,896,800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR       # ≈ 8.478e-8

    def __init__(self, tickers: list[str],
                 dt: float = DEFAULT_DT,
                 event_probability: float = 0.001) -> None: ...

    def step(self) -> dict[str, float]: ...   # hot path, called every 500 ms
    def add_ticker(self, ticker: str) -> None: ...
    def remove_ticker(self, ticker: str) -> None: ...
    def get_price(self, ticker: str) -> float | None: ...
    def get_tickers(self) -> list[str]: ...

    # internals
    def _add_ticker_internal(self, ticker: str) -> None: ...   # no Cholesky rebuild (batch init)
    def _rebuild_cholesky(self) -> None: ...
    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float: ...
```

State: `_tickers: list[str]`, `_prices: dict[str, float]`, `_params: dict[str, dict]`,
`_cholesky: np.ndarray | None`.

### 4.2 `step()` — pseudocode

```
n ← len(tickers); if n = 0 → {}
Z ← standard_normal(n)
Z ← cholesky @ Z                    if cholesky is not None
for i, ticker in enumerate(tickers):
    drift     ← (mu − 0.5·sigma²) · dt
    diffusion ← sigma · sqrt(dt) · Z[i]
    price    ← price · exp(drift + diffusion)
    if rand() < event_probability:
        price ← price · (1 + uniform(0.02, 0.05) · choice(−1, +1))
    out[ticker] ← round(price, 2)
return out
```

Complexity `O(n²)` per tick with the matrix multiply, `O(n)` without. At n = 10 and 2 Hz this is
microseconds — the loop is dominated by `asyncio.sleep`, not by math.

### 4.3 `SimulatorDataSource`

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache,
                 update_interval: float = 0.5,
                 event_probability: float = 0.001) -> None: ...
```

* `start(tickers)` → build `GBMSimulator`, **seed the cache** with initial prices (so the first SSE
  frame and the first page render are populated), `create_task(_run_loop)`.
* `add_ticker()` → `sim.add_ticker()` **and** an immediate `cache.update()` for the new symbol.
* `remove_ticker()` → `sim.remove_ticker()` **and** `cache.remove()`.
* `stop()` → cancel, `await` the task, swallow `CancelledError`, clear the handle. Idempotent.
* `_run_loop()` → `step()` → `cache.update()` per ticker → `sleep(interval)`, wrapped in
  `try/except Exception: logger.exception(...)` so one bad tick never kills the feed.

---

## 5. Module boundaries

```
backend/app/market/
├── seed_prices.py   # constants: prices, params, correlation groups/coefficients
├── simulator.py     # GBMSimulator (math) + SimulatorDataSource (async adapter)
├── cache.py         # PriceCache — the simulator's only sink
└── models.py        # PriceUpdate — built inside PriceCache.update()
```

`seed_prices.py` must stay **declarative**. Any derived value (matrices, drift terms, normalized
weights) is computed in `simulator.py` or it becomes untestable and stale.

---

## 6. Determinism and testing

Today the simulator uses module-level `random` and `np.random.standard_normal`, so prices differ run
to run. Recommended change (no API break): accept an injected RNG pair.

```python
def __init__(self, tickers, dt=DEFAULT_DT, event_probability=0.001,
             np_rng: np.random.Generator | None = None,
             py_rng: random.Random | None = None):
    self._np_rng = np_rng or np.random.default_rng()
    self._py_rng = py_rng or random.Random()
```

Then `GBMSimulator(tickers, np_rng=np.random.default_rng(42), py_rng=random.Random(42))` replays
byte-identically — a hard requirement for snapshot/SSE tests.

Test matrix (`backend/tests/market/test_simulator.py`, `test_simulator_source.py`):

| Assertion | Why |
|---|---|
| Prices stay finite and `> 0` over 10k ticks | `exp` overflow/underflow, price collapse |
| Deterministic with a fixed seed (same draw sequence) | reproducibility |
| `step()` returns exactly the tracked tickers, rounded 2dp | cache/UI contract |
| `add_ticker` mid-run doesn't perturb existing prices | no state corruption on rebuild |
| `remove_ticker` is idempotent; unknown ticker is a no-op | watchlist churn |
| Correlation ≈ target: sample 5k steps, check Pearson ρ within ±0.1 | proves Cholesky is wired up |
| Event frequency ≈ `event_probability` over 100k ticks | tuning drift |
| `start()` seeds the cache before the first tick | first-paint correctness |
| `stop()` halts cache writes; loop survives a raised exception | lifecycle contract |
| `dt` calibration: session σ ≈ `sigma / √252` | guards against a unit mistake |

Pearson checks are the one test people skip; without them, a transposed or mis-ordered `L` still
produces "plausible" prices and the bug survives for months.

---

## 7. Numerical safety

**7.1 Positivity.** GBM is multiplicative, so prices can never be ≤ 0 — but they can *underflow* to
denormal values after a long run of down-shocks. Add a floor:

```python
self._prices[ticker] = max(self._prices[ticker], 0.01)
```

**7.2 Positive semidefiniteness.** `np.linalg.cholesky` raises `LinAlgError` for a matrix that is not
PD. The current constants are safe; arbitrary future correlations (e.g. one ticker at 0.95 with two
that are 0.1 with each other) are not. Guard the rebuild:

```python
try:
    self._cholesky = np.linalg.cholesky(corr)
except np.linalg.LinAlgError:
    jitter = 1e-8 * np.eye(n)
    self._cholesky = np.linalg.cholesky(corr + jitter)   # or fall back to None
```

Never let a watchlist edit crash the app. A degraded (uncorrelated) simulation beats a 500.

**7.3 Unbounded drift from shocks.** Each shock is 2–5% and never reverts. Over hours of uptime the
price can wander ±40%. If long-running realism matters, add a soft mean-reversion term toward the
seed price (an Ornstein–Uhlenbeck overlay) or clamp cumulative drift to ±50% of the seed.

**7.4 Rounding.** `step()` rounds to 2dp; `PriceCache.update()` also rounds. Double rounding is
harmless and keeps the value that flashes in the UI identical to the value stored. Do not round
*inside* the GBM multiplication — small prices would stall at 0.01.

---

## 8. Tuning guide

| Knob | Location | Default | Effect |
|---|---|---|---|
| `update_interval` | `SimulatorDataSource` / SSE | 0.5 s | Feed cadence; changing it invalidates `dt` |
| `dt` | `GBMSimulator` | `0.5 / 5_896_800` | Simulated time per tick; keep 1:1 with the interval |
| `sigma` | `TICKER_PARAMS` | 0.17–0.50 | Intraday amplitude; annualized |
| `mu` | `TICKER_PARAMS` | 0.03–0.08 | Negligible at these horizons |
| `event_probability` | `GBMSimulator` | 0.001 | Drama dial; 0.005 ≈ an event every 10 s with 10 tickers |
| shock range | `step()` | 2–5% | Visual impact of an event |
| correlation constants | `seed_prices.py` | 0.3/0.5/0.6 | "Market mood" coherence |
| seed prices | `seed_prices.py` | illustrative | Realism of absolute levels |

Rules of thumb:

* Want a livelier demo? Raise `event_probability` before raising `sigma`. Sigma changes the texture of
  the whole tape; events add punctuation.
* Want it calmer for screenshots? Lower shock magnitude to 1–2%, keep frequency.
* Adding many tickers? Watch the correlation test — a wide, dense matrix is where Cholesky breaks.

---

## 9. Performance

* `step()`: ~10 µs for 10 tickers (two numpy calls plus a Python loop). 2 Hz → negligible CPU.
* Memory: three dicts of size n. No price history is retained — **sparklines are built client-side**
  from the SSE stream, by design (`PLAN.md` §2).
* The Cholesky rebuild is the only expensive operation and it happens on watchlist mutation only.
* The loop must remain exception-isolated; a single `ZeroDivisionError` in a bad code path should not
  take down the feed.

---

## 10. Alternatives considered

| Approach | Why not |
|---|---|
| Independent random walks | Watchlist flashes incoherently; reads as fake |
| AR(1) / mean reversion only | Produces mean-reverting noise with no trends; less convincing |
| Historical replay (loop a recorded day) | Deterministic and realistic, but needs shipped data and repeats visibly |
| Bootstrap from real returns | Best realism; needs a historical dataset and licensing care |
| Agent-based / order book | Massive complexity for a simulated portfolio demo |
| **GBM + correlated shocks** | Chosen: standard, explainable, cheap, positive-by-construction |

---

## 11. Extension roadmap

Ordered by value per unit of complexity:

1. **Injected RNG** (§6) — required for reliable tests. *Highest value, lowest cost.*
2. **PSD guard** (§7.2) and **price floor** (§7.1) — robustness, ~5 lines.
3. **Session awareness** — flatten `dt` outside 09:30–16:00 ET, or make the simulator "closed" with
   the market-status gate used by the Massive path. Prevents overnight drift.
4. **Volatility clustering** — scale `sigma` by a slowly varying latent factor (stochastic volatility)
   so quiet and active periods alternate.
5. **OU / mean-reversion overlay** toward the seed price, bounding long-run drift.
6. **Volume and spread** — synthetic `volume`, `bid`/`ask` around the mid, enabling a future order-book
   or slippage model.
7. **Index factor** — one latent market factor plus sector betas, replacing the pairwise matrix; this
   scales to hundreds of tickers without an `O(n³)` rebuild.

---

## 12. Sources

* This repository: `backend/app/market/simulator.py`, `seed_prices.py`, `cache.py`;
  `backend/tests/market/test_simulator.py`, `test_simulator_source.py`;
  `planning/PLAN.md` §6 (Market Data).
* Geometric Brownian Motion and Itô calculus (standard results; the `(μ − σ²/2)` drift correction and
  lognormal distribution) — any quantitative-finance textbook, e.g. Hull, *Options, Futures, and Other
  Derivatives*.
* Cholesky decomposition for correlated normals; positive-definiteness requirements —
  <https://numpy.org/doc/stable/reference/generated/numpy.linalg.cholesky.html> (accessed 18 Nov 2026).
* `numpy.random.Generator` / `default_rng` for reproducible draws —
  <https://numpy.org/doc/stable/reference/random/generator.html> (accessed 18 Nov 2026).
* Massive API plan/entitlement context that motivates the simulator fallback — see `MASSIVE_API.md` §3.
