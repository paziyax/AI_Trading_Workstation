"""GBM simulator math."""

from __future__ import annotations

import math
import random

import numpy as np
import pytest

from app.market.seed_prices import SEED_PRICES, UNKNOWN_SEED_RANGE
from app.market.simulator import GBMSimulator


def make(tickers: list[str], **kwargs: object) -> GBMSimulator:
    kwargs.setdefault("np_rng", np.random.default_rng(7))
    kwargs.setdefault("py_rng", random.Random(7))
    return GBMSimulator(tickers, **kwargs)  # type: ignore[arg-type]


def log_returns(prices: list[float]) -> np.ndarray:
    values = np.asarray(prices, dtype=float)
    return np.diff(np.log(values))


def test_known_tickers_start_at_seed_prices() -> None:
    sim = make(["AAPL", "MSFT"])
    assert sim.get_price("AAPL") == pytest.approx(SEED_PRICES["AAPL"])
    assert sim.get_price("MSFT") == pytest.approx(SEED_PRICES["MSFT"])


def test_unknown_ticker_seed_is_within_range() -> None:
    sim = make(["ZZZZ"])
    price = sim.get_price("ZZZZ")
    assert price is not None
    assert UNKNOWN_SEED_RANGE[0] <= price <= UNKNOWN_SEED_RANGE[1]


def test_step_returns_every_tracked_ticker_rounded_to_cents() -> None:
    sim = make(["AAPL", "MSFT", "NVDA"])
    prices = sim.step()
    assert set(prices) == {"AAPL", "MSFT", "NVDA"}
    for price in prices.values():
        assert price == round(price, 2)


def test_step_is_deterministic_with_injected_rngs() -> None:
    first = make(["AAPL", "MSFT"])
    second = make(["AAPL", "MSFT"])
    for _ in range(50):
        assert first.step() == second.step()


def test_prices_stay_positive_over_a_long_run() -> None:
    sim = make(["TSLA", "NVDA"], dt=1.0, event_probability=0.01)
    for _ in range(10_000):
        for price in sim.step().values():
            assert math.isfinite(price)
            assert price > 0


def test_dt_is_calibrated_to_a_trading_year() -> None:
    assert GBMSimulator.TRADING_SECONDS_PER_YEAR == 5_896_800
    assert GBMSimulator.DEFAULT_DT == pytest.approx(0.5 / 5_896_800)
    assert make(["AAPL"]).dt == pytest.approx(0.5 / 5_896_800)


def test_per_tick_volatility_matches_sigma_times_sqrt_dt() -> None:
    """NVDA: sigma 0.40 at $800, so cent rounding is negligible against the move size."""
    sim = make(["NVDA"], event_probability=0.0)
    prices = [SEED_PRICES["NVDA"]]
    for _ in range(20_000):
        prices.append(sim.step()["NVDA"])

    realised = float(np.std(log_returns(prices), ddof=1))
    expected = 0.40 * math.sqrt(GBMSimulator.DEFAULT_DT)
    assert realised == pytest.approx(expected, rel=0.05)


def test_tech_tickers_are_correlated() -> None:
    # Bigger dt than production: at 500 ms ticks a cent of rounding swamps the move size and
    # the measured correlation collapses toward zero.
    sim = make(["AAPL", "MSFT"], dt=1e-3, event_probability=0.0)
    aapl = [SEED_PRICES["AAPL"]]
    msft = [SEED_PRICES["MSFT"]]
    for _ in range(10_000):
        prices = sim.step()
        aapl.append(prices["AAPL"])
        msft.append(prices["MSFT"])

    rho = float(np.corrcoef(log_returns(aapl), log_returns(msft))[0, 1])
    assert rho == pytest.approx(0.6, abs=0.1)


def test_no_events_when_probability_is_zero() -> None:
    sim = make(["AAPL"], event_probability=0.0)
    prices = [SEED_PRICES["AAPL"]]
    for _ in range(1_000):
        prices.append(sim.step()["AAPL"])
    assert float(np.max(np.abs(log_returns(prices)))) < 0.01


def test_events_dominate_when_probability_is_one() -> None:
    sim = make(["AAPL"], event_probability=1.0)
    prices = [SEED_PRICES["AAPL"]]
    for _ in range(200):
        prices.append(sim.step()["AAPL"])
    assert float(np.min(np.abs(log_returns(prices)))) > 0.015


def test_add_ticker_is_idempotent_and_appends_once() -> None:
    sim = make(["AAPL"])
    sim.add_ticker("msft")
    sim.add_ticker("MSFT")
    assert sim.get_tickers() == ["AAPL", "MSFT"]
    assert sim.get_price("MSFT") == pytest.approx(SEED_PRICES["MSFT"])


def test_constructor_dedupes_tickers() -> None:
    sim = make(["AAPL", "aapl", "AAPL"])
    assert sim.get_tickers() == ["AAPL"]
    assert set(sim.step()) == {"AAPL"}


def test_remove_ticker_is_idempotent() -> None:
    sim = make(["AAPL", "MSFT"])
    sim.remove_ticker("AAPL")
    sim.remove_ticker("AAPL")
    sim.remove_ticker("NOPE")
    assert sim.get_tickers() == ["MSFT"]
    assert sim.get_price("AAPL") is None


def test_get_tickers_returns_a_copy() -> None:
    sim = make(["AAPL"])
    tickers = sim.get_tickers()
    tickers.append("MSFT")
    assert sim.get_tickers() == ["AAPL"]


def test_empty_simulator_returns_no_prices() -> None:
    assert make([]).step() == {}


def test_invalid_parameters_are_rejected() -> None:
    with pytest.raises(ValueError):
        make(["AAPL"], dt=0)
    with pytest.raises(ValueError):
        make(["AAPL"], event_probability=1.5)


def test_single_ticker_skips_cholesky() -> None:
    sim = make(["AAPL"])
    assert sim._cholesky is None  # noqa: SLF001 - structural guarantee


def test_cholesky_failure_is_retried_with_a_jittered_diagonal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = np.linalg.cholesky
    calls = {"n": 0}

    def flaky(matrix: np.ndarray) -> np.ndarray:
        calls["n"] += 1
        if calls["n"] == 1:
            raise np.linalg.LinAlgError("not positive definite")
        return real(matrix)

    monkeypatch.setattr(np.linalg, "cholesky", flaky)
    sim = make(["AAPL", "MSFT"])

    assert calls["n"] == 2
    assert sim._cholesky is not None  # noqa: SLF001
    assert set(sim.step()) == {"AAPL", "MSFT"}


def test_cholesky_failure_degrades_to_independent_draws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def always_fails(matrix: np.ndarray) -> np.ndarray:
        raise np.linalg.LinAlgError("never")

    monkeypatch.setattr(np.linalg, "cholesky", always_fails)
    sim = make(["AAPL", "MSFT"])

    assert sim._cholesky is None  # noqa: SLF001
    assert set(sim.step()) == {"AAPL", "MSFT"}


def test_watchlist_churn_does_not_corrupt_prices() -> None:
    sim = make(["AAPL", "MSFT"])
    for ticker in ["NVDA", "TSLA", "GOOGL", "ZZZZ"]:
        sim.add_ticker(ticker)
    sim.step()
    for ticker in ["NVDA", "TSLA"]:
        sim.remove_ticker(ticker)
    prices = sim.step()
    assert set(prices) == {"AAPL", "MSFT", "GOOGL", "ZZZZ"}
    assert all(math.isfinite(p) and p > 0 for p in prices.values())
