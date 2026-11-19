import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePriceFlash } from "@/hooks/usePriceFlash";

function Probe({ price }: { price: number | null }) {
  const flash = usePriceFlash(price);
  return <span data-testid="price" data-flash={flash} />;
}

describe("price flash", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("flashes down on a downtick", () => {
    const { rerender } = render(<Probe price={191} />);
    expect(screen.getByTestId("price")).toHaveAttribute("data-flash", "none");
    rerender(<Probe price={190.5} />);
    expect(screen.getByTestId("price")).toHaveAttribute("data-flash", "down");
  });

  it("flashes up, then returns to none after 500 ms", () => {
    const { rerender } = render(<Probe price={100} />);
    rerender(<Probe price={101} />);
    expect(screen.getByTestId("price")).toHaveAttribute("data-flash", "up");

    act(() => {
      vi.advanceTimersByTime(499);
    });
    expect(screen.getByTestId("price")).toHaveAttribute("data-flash", "up");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByTestId("price")).toHaveAttribute("data-flash", "none");
  });

  it("does not restart the timer when the same price repeats", () => {
    const { rerender } = render(<Probe price={100} />);
    rerender(<Probe price={101} />);
    act(() => {
      vi.advanceTimersByTime(250);
    });
    rerender(<Probe price={101} />);
    expect(screen.getByTestId("price")).toHaveAttribute("data-flash", "up");

    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(screen.getByTestId("price")).toHaveAttribute("data-flash", "none");
  });
});
