import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Sparkline } from "@/components/Sparkline";
import { priceFrame } from "@/test/fixtures";
import { MockEventSource } from "@/test/mockEventSource";
import { PricesProvider, usePrices } from "@/providers/PricesProvider";

function Probe() {
  const { connection, history, prices } = usePrices();
  return (
    <div>
      <span data-testid="connection">{connection}</span>
      <span data-testid="price">{prices.AAPL?.price ?? "none"}</span>
      <span data-testid="samples">{history.AAPL?.length ?? 0}</span>
    </div>
  );
}

describe("live price stream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("creates exactly one EventSource at the contract URL", () => {
    render(
      <PricesProvider>
        <Probe />
      </PricesProvider>,
    );
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe("/api/stream/prices");
    expect(screen.getByTestId("connection")).toHaveTextContent("reconnecting");
  });

  it("maps open, error and ten-second silence to the connection contract", () => {
    render(
      <PricesProvider>
        <Probe />
      </PricesProvider>,
    );
    const source = MockEventSource.latest!;

    act(() => source.emitOpen());
    expect(screen.getByTestId("connection")).toHaveTextContent("connected");

    act(() => source.emitFrame(priceFrame));
    expect(screen.getByTestId("price")).toHaveTextContent("192");
    expect(screen.getByTestId("samples")).toHaveTextContent("1");

    act(() => source.emitError());
    expect(screen.getByTestId("connection")).toHaveTextContent("reconnecting");

    act(() => {
      vi.advanceTimersByTime(9_000);
    });
    expect(screen.getByTestId("connection")).toHaveTextContent("reconnecting");

    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(screen.getByTestId("connection")).toHaveTextContent("disconnected");

    act(() => source.emitFrame(priceFrame));
    expect(screen.getByTestId("connection")).toHaveTextContent("connected");
  });

  it("replaces the price map wholesale on every frame", () => {
    render(
      <PricesProvider>
        <Probe />
      </PricesProvider>,
    );
    act(() => MockEventSource.latest!.emitFrame(priceFrame));
    act(() =>
      MockEventSource.latest!.emitFrame({
        AAPL: { ...priceFrame.AAPL, price: 193, previous_price: 192 },
      }),
    );
    expect(screen.getByTestId("price")).toHaveTextContent("193");
  });
});

describe("sparkline reservation", () => {
  it("renders an empty SVG until two samples exist", () => {
    const { rerender } = render(<Sparkline ticker="AAPL" samples={[190]} />);
    const svg = screen.getByTestId("watchlist-sparkline-AAPL");
    expect(svg).toHaveAttribute("data-samples", "1");
    expect(svg.querySelector("polyline")).toBeNull();

    rerender(<Sparkline ticker="AAPL" samples={[190, 191]} />);
    expect(svg.querySelector("polyline")).not.toBeNull();
    expect(svg).toHaveAttribute("data-tone", "up");
  });
});
