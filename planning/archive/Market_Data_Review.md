# Market Data Backend — Code Review

**Reviewed:** 19 Nov 2026
**Scope:** `backend/app/market/` (11 modules) and `backend/tests/market/` (11 test modules)
**Docs read:** `PLAN.md` §6/§8/§14, `MARKET_DATA_SUMMARY.md`, `archive/Market_Data_Design.md`,
`archive/MARKET_INTERFACE.md`, `archive/MARKET_SIMULATOR.md`, `archive/MASSIVE_API.md`
**Environment:** Python 3.14.6, `massive` 2.2.0, numpy 2.4.2, fastapi 0.128.7, pytest 9.0.2

---

## 1. Verdict

**Ship it.** The component is well structured, fully tested, and behaves as documented. No critical
or high-severity defects were found. There is **one medium-severity fidelity bug** (vendor
`lastTrade` timestamps are silently replaced with wall-clock time) and **one medium-severity
efficiency bug** (EOD mode re-fetches forever if a watchlist ticker has no vendor row).

| Area | Result |
|---|---|
| Test suite | **150 passed**, 3 consecutive runs, no flakes |
| Statement coverage | **100%** (615/615 statements) |
| `ruff check` | Clean |
| `ruff format --check` | **7 files would reformat** |
| Layering | Correct — no cycles, `cache`/`models`/`stream` never import a source |
| Contract enforcement | Conformance suite runs against **3** source configurations |

---

## 2. Verification evidence

```
$ uv run --module pytest -q --cov=app --cov-report=term-missing
150 passed in 2.52s

app\market\cache.py           41      0   100%
app\market\config.py          53      0   100%
app\market\factory.py         18      0   100%
app\market\interface.py       60      0   100%
app\market\massive_client.py 203      0   100%
app\market\models.py          30      0   100%
app\market\seed_prices.py      8      0   100%
app\market\simulator.py      159      0   100%
app\market\stream.py          36      0   100%
TOTAL                        615      0   100%
```

Repeatability (timing-sensitive asyncio tests are the usual flake source):

```
run 1: 150 passed in 2.05s
run 2: 150 passed in 2.38s
run 3: 150 passed in 2.05s
```

Test distribution: `test_massive_source` 28, `test_conformance` 23, `test_simulator` 20,
`test_massive_helpers` 15, `test_cache` 12, `test_config` 11, `test_simulator_source` 11,
`test_stream` 9, `test_interface` 8, `test_models` 7, `test_factory` 6.

---

## 3. What is genuinely good

1. **One-directional dependencies.** `config → models → interface → cache → stream`, with sources
   plugging in at the factory. `cache.py`, `models.py` and `stream.py` import nothing from
   `simulator.py` or `massive_client.py`. This is what makes the conformance suite possible.
2. **The conformance suite is real.** The same six invariants run against simulator, Massive-EOD and
   Massive-snapshot. Most projects claim an interface and test one implementation.
3. **Health is data-driven, not a state machine.** `last_success_at` + `consecutive_failures` +
   `mode` lets the UI compute the dot; no reconnect logic to rewrite later.
4. **Rounding at the write boundary.** 2 dp on write means `change` is exact at cent precision and
   flash animations cannot fire on float noise. `previous_price` reuses the stored value, so
   re-rounding is a no-op — a small detail that is easy to get wrong and is right here.
5. **Determinism is designed in, not bolted on.** `np_rng` / `py_rng` injection makes the GBM replay
   byte-identically, and the tests exploit it.
6. **Plan capability is explicit.** `MASSIVE_PLAN` with `basic` as the default is the correct
   pessimistic choice; a free key genuinely 403s on snapshots.
7. **Degradation paths are tested, not assumed.** 403-at-startup, 403-mid-loop, transient 5xx with
   backoff, empty EOD response, holiday walk-back, market-closed skip — all have tests.
8. **`stop()` is correctly cancellation-safe.** `except Exception` (not `BaseException`) in every
   loop means `CancelledError` propagates; no cache writes after `stop()` returns.

---

## 4. Findings

| ID | Severity | Finding |
|---|---|---|
| F-01 | **Medium** | `lastTrade` timestamps are never used — silently replaced by wall clock |
| F-02 | **Medium** | EOD refetches every cycle if any watched ticker has no vendor row |
| F-03 | Low | Non-positive prices are accepted into the cache |
| F-04 | Low | `SimulatorDataSource(interval=…)` does not recompute `dt` |
| F-05 | Low | `market closed` note cannot clear a prior failure — dot stays red |
| F-06 | Low | `to_unix_seconds` milliseconds boundary is exclusive |
| F-07 | Info | Nanosecond branch of `to_unix_seconds` is unreachable with real payloads |
| F-08 | Low | `ruff format --check` fails on 7 files |
| F-09 | Low | Dead code: `Plan.snapshot_delay_minutes`, `EOD_ROWS` in conformance test |
| F-10 | Info | `cache.py` docstring misstates why the lock exists |
| F-11 | Info | Micro-perf: RNG call per ticker at `p=0`; `sqrt(dt)` recomputed per ticker |
| F-12 | **Medium** | `MARKET_DATA_SUMMARY.md` verify section is stale (deleted `.pydeps`) |
| F-13 | Low | Docs specify `massive 2.10+`; lockfile resolves **2.2.0** |
| F-14 | Low | `MARKET_INTERFACE.md` backlog table lists implemented items as gaps |
| F-15 | Info | `.gitignore` still carries `.pydeps/` with a now-false comment |
| F-16 | Info | Design-doc acceptance criteria need app wiring that does not exist yet |
| F-17 | **Medium** | No CI workflow runs the backend tests |
| F-18 | **Medium** | The `last_trade` test double is more permissive than the real model (root cause of F-01) |
| F-19 | Low | Coverage is 100% but not enforced (`fail_under` absent) |

---

## 5. Medium-severity findings in detail

### F-01 — `lastTrade` timestamps are never used

`massive_client.py:58-69` walks a precedence chain and reads the timestamp generically:

```python
return float(value), to_unix_seconds(getattr(bar, "timestamp", None))
```

In `massive` 2.2.0 the real `LastTrade` model has **no `timestamp` attribute**:

```
>>> hasattr(LastTrade, "timestamp")
False
>>> [f.name for f in dataclasses.fields(LastTrade)]
['ticker', 'trf_timestamp', 'sequence_number', 'sip_timestamp', 'participant_timestamp',
 'conditions', 'correction', 'id', 'price', 'trf_id', 'size', 'exchange', 'tape']
```

So for the highest-precedence branch the `getattr` default returns `None`, `PriceCache.update`
substitutes `time.time()`, and the price is stamped with the **local receive time instead of the
vendor trade time**. No crash — but the documented ns→s normalization never happens on the path that
matters most (Advanced plans, where `last_trade` is populated).

Note that `min`, `day` and `prev_day` are fine: `MinuteSnapshot.timestamp` and `Agg.timestamp` both
exist and are milliseconds.

**Impact:** timestamps are wrong by the network delay plus any batching, and any future
"stale price" logic that trusts `PriceUpdate.timestamp` would be measuring the wrong clock.
Price values themselves are unaffected.

**Recommendation:** for the `last_trade` branch fall back to a field that exists — `snapshot.updated`
(nanoseconds, already modelled on `TickerSnapshot`), or `sip_timestamp` / `participant_timestamp`.
Add a test that builds a real `LastTrade`-shaped object rather than a `SimpleNamespace`.

### F-02 — EOD mode refetches forever when a ticker is unpriceable

`massive_client.py:256-267` decides staleness with:

```python
stale = force or self._eod_day != day or any(
    self._cache.get(t) is None for t in self._tickers
)
```

If a watched ticker never appears in the grouped-daily response (delisted, mistyped, not yet
published), `cache.get(t)` stays `None` **forever**, so `stale` is permanently `True`. Verified:

```
start(["AAPL","MSFT"]) with only AAPL in the vendor response
after start  -> calls=1, cache.version=1
two more _refresh_eod() -> calls=3, cache.version=3
```

Consequences: one wasted API call every 30 minutes for the life of the process, every cached price
rewritten on each cycle (defeating the "don't rewrite unchanged prices" optimization the code
deliberately implements), and no health signal that a ticker is unpriceable.

**Recommendation:** compute staleness only over tickers the vendor actually returned
(`t in prices`), and record the remainder as `health.detail` (e.g. `"2026-11-24 close, 1 unpriced"`).
That keeps the API budget honest on a free key, where 5 calls/minute is the whole budget.

### F-17 — No CI gate

`.github/workflows/` contains only `opencode.yml` and `opencode-review.yml`; nothing runs
`pytest` or `ruff`. Given 150 tests exist and pass in ~2 s, adding a two-step job is cheap insurance
against the suite silently rotting before the portfolio/chat work lands.

### F-18 — Test double hides F-01

`tests/market/conftest.py:88` builds the fake as:

```python
last_trade=bar(price=self.prices[ticker], timestamp=1794972600512000000)
```

The real `LastTrade` has no `timestamp`. The fake is therefore **strictly more capable than
production**, which is exactly why a green suite did not catch F-01. Fakes for third-party models
should mirror the real field set; where a field is absent in reality, the test should assert the
fallback behaviour instead.

---

## 6. Low and informational findings

**F-03 — non-positive prices accepted.** `PriceCache.update` rounds but does not validate:
`cache.update("AAPL", 0.0)` yields `price=0.0, direction="flat", change_percent=0.0`. A single bad
vendor row would propagate a zero into portfolio valuation and P&L. A one-line guard
(`if value <= 0: raise ValueError` or skip-and-record) is cheap; the simulator already floors at
`0.01`, so this is purely about the vendor path.

**F-04 — `interval` and `dt` are decoupled.** `SimulatorDataSource.__init__` accepts `interval`,
but `GBMSimulator` is always constructed with `DEFAULT_DT` (0.5 s). Verified: `interval=5.0` leaves
`dt == DEFAULT_DT`. Simulated time then runs 10× slower than wall clock, silently rescaling
volatility. `MARKET_SIMULATOR.md` documents the hazard, but the code does not enforce it. Either
derive `dt = interval / TRADING_SECONDS_PER_YEAR` inside the adapter, or reject `interval != 0.5`.

**F-05 — `note()` cannot clear a failure.** After a failed startup followed by a closed market:

```
connected=False, consecutive_failures=1, detail="market closed"
```

The header would render red with "market closed" — contradictory, and it stays that way until the
market reopens. Either have the closed-market branch call `success()` with the note (a closed market
is a healthy state, not an error), or let the UI treat `detail == "market closed"` as neutral.

**F-06 — milliseconds boundary.** `to_unix_seconds` uses `ts > 10**12`, so exactly `10**12` ms is
read as `10**12` **seconds** (year 33658). Unreachable with current market data; worth a `>=` and a
boundary test since the function is the sole guard against a decade-scale timestamp bug.

**F-07 — ns branch unreachable in practice.** Every timestamp field reachable through
`extract_price` is milliseconds, so the `ts > 10**17` branch only ever runs in tests. Harmless
defensive code, but it creates a false impression that ns handling is exercised end to end. If F-01
is fixed using `snapshot.updated`, this branch becomes live and should get a real-shape test.

**F-08 — formatting.** `ruff check` passes but `ruff format --check` reports 7 files. All differences
are line-wrapping (e.g. the `stale = (...)` expression in `_refresh_eod`). Either run
`uv run --module ruff format app tests` once, or add `format` to the ignore set so the state is
intentional rather than accidental.

**F-09 — dead code.** `Plan.snapshot_delay_minutes` is referenced only by `test_config.py`; no
production code consumes it. `EOD_ROWS` at `test_conformance.py:20` is assigned and never used.
Both are harmless but are the kind of thing that reads as "unfinished".

**F-10 — lock rationale.** `cache.py` says the lock exists "because the Massive path writes from
`asyncio.to_thread`". In fact `_refresh_snapshot` only *fetches* in a thread
(`await asyncio.to_thread(self._fetch_snapshot_batch)`) and writes on the loop thread. The lock is
still correct and worth keeping (it is cheap, and it future-proofs for a real threaded writer), but
the comment states a reason that is not true. Say "guards against a future threaded writer" instead.

**F-11 — micro-perf.** `step()` calls `self._py_rng.random()` once per ticker even when
`event_probability == 0`, and recomputes `math.sqrt(self._dt)` per ticker. At 10 tickers and 2 Hz
this is noise, but hoisting both out of the loop is free.

---

## 7. Documentation drift

| Doc | Issue |
|---|---|
| `MARKET_DATA_SUMMARY.md:35-42` | **F-12.** Says `uv sync` cannot create a venv (os error 4551) and instructs `PYTHONPATH="$PWD;$PWD\.pydeps"`. `backend/.pydeps` has been deleted and `uv sync`/`uv run` now work. This section will actively mislead the next agent. |
| `MARKET_DATA_SUMMARY.md:32` | Says `uv run pytest`; on this machine that form is blocked by Smart App Control. Should read `uv run --module pytest` (as `backend/README.md` already does). |
| `Market_Data_Design.md:4` | **F-13.** "massive 2.10+"; the lockfile resolves **2.2.0**. Call sites are compatible (verified below), but the version claim is wrong. |
| `MARKET_INTERFACE.md:197-210` | **F-14.** "Backlog — documented vs implemented" lists `lastTrade` fallback, ns normalization, plan capability, EOD mode, backoff, `MARKET_DATA_SOURCE`, and health as **gaps**. All are implemented. |
| `Market_Data_Design.md` §14 | **F-16.** Acceptance criteria require lifespan wiring, `/api/market/status`, and a running app; `backend/app/main.py` does not exist yet. Correctly deferred, but the checklist cannot be ticked as written. |
| `.gitignore` | **F-15.** `.pydeps/` retained with the comment "used for test runs when uv cannot create a venv". Both halves are now false. |

**Verified compatibility (good news).** The call sites match the *installed* client, so F-13 is a
documentation problem only:

```
get_snapshot_all(self, market_type, tickers=None, ...)            ✓ used with market_type=, tickers=
get_grouped_daily_aggs(self, date, adjusted=None, ...)            ✓ used with date=, adjusted=
get_market_status(self)                                            ✓
SnapshotMarketType.STOCKS                                          ✓
TickerSnapshot.ticker / .last_trade / .min / .day / .prev_day      ✓
GroupedDailyAgg.ticker / .close / .timestamp                       ✓
MarketStatus.market                                                ✓
LastTrade.price                                                    ✓
LastTrade.timestamp                                                ✗ (see F-01)
```

---

## 8. Test-suite assessment

**Strengths.** Deterministic RNG injection; conformance across three source configurations;
idempotency tested for `start`, `stop`, `add_ticker`, `remove_ticker`; the Cholesky failure path is
covered twice (jittered retry, full degradation); Pearson ρ within ±0.1 catches a transposed factor;
`stop()` freeze is asserted on `cache.version` rather than a sleep-and-hope; SSE framing asserts the
exact bytes (`retry: 1000`, `: keep-alive`).

**Gaps worth closing, in priority order.**

1. A `LastTrade`-shaped fixture (F-01/F-18) — the single highest-value test to add.
2. A watched ticker missing from the EOD response (F-02) — assert one call per cycle, not two.
3. `PriceCache` under real threads — the lock is currently only exercised single-threaded. I ran
   4 threads × 2 000 mixed reads/writes/writes-snapshots manually: **no errors, version 8 000,
   correct key count**. That should be a test, not a one-off.
4. A non-positive price rejection test (F-03).
5. `stop()` called before `start()` on `SimulatorDataSource` (only the Massive path covers this).
6. An HTTP-level SSE test via `TestClient`; the current test calls the route endpoint directly, so
   `StreamingResponse` behaviour over a real socket (buffering, header casing) is unverified.
7. Two simultaneous SSE clients against one cache — the map-replace contract should hold for both.

**Coverage policy (F-19).** 100% is achieved but not enforced; `[tool.coverage.report]` has no
`fail_under`. Add `fail_under = 95` (or 100) so a future refactor cannot quietly drop it.

---

## 9. Recommended order of work

1. **F-01** — fix the `lastTrade` timestamp fallback, with a real-shape fixture. *(Correctness.)*
2. **F-02** — scope EOD staleness to tickers the vendor returned. *(API budget + correctness of the
   no-rewrite optimization.)*
3. **F-12** — rewrite the `MARKET_DATA_SUMMARY.md` verify section; it currently sends the next agent
   down a dead path. *(Cheap, high value.)*
4. **F-17** — add a `pytest` + `ruff` CI job. *(Prevents regression of everything above.)*
5. **F-05**, **F-03** — health semantics and a positive-price guard. *(Small, user-visible.)*
6. **F-08**, **F-09**, **F-15** — one-shot formatting and dead-code cleanup.
7. **F-04** — decide the `interval`/`dt` contract before anyone tunes the tick rate.

Items F-06, F-07, F-10, F-11 are informational; fix them if you are already in the file.

---

## 10. Explicitly out of scope

Not defects of this component, listed so they are not mistaken for review gaps:

- `backend/app/main.py`, the FastAPI lifespan, `/api/market/status`, and `/api/health` are not built.
  `MARKET_DATA_SUMMARY.md` §"Next" correctly defers them.
- Portfolio, trading, chat, and SQLite persistence are separate components.
- Docker, the frontend, and E2E tests are untouched by this review.

---

## 11. Bottom line

The market data layer does what its design document says, and the test suite proves it. Two
behavioural defects deserve a fix before the layer is wired into the app — the vendor timestamp
fallback (F-01) and the EOD refetch loop (F-02) — plus one documentation section that is now
actively wrong (F-12). Everything else is polish, and none of it blocks building the portfolio and
chat layers on top of this interface.
