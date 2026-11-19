import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WatchlistPanel } from "@/components/WatchlistPanel";
import { jsonResponse, watchlistFixture, installFetch, installDefaultApi } from "@/test/fixtures";
import { MockEventSource } from "@/test/mockEventSource";
import { PricesProvider } from "@/providers/PricesProvider";
import { WatchlistProvider } from "@/providers/WatchlistProvider";

function renderPanel({
  selectedTicker = "AAPL",
  onSelect = vi.fn(),
}: {
  selectedTicker?: string | null;
  onSelect?: (ticker: string) => void;
} = {}) {
  return render(
    <PricesProvider>
      <WatchlistProvider>
        <WatchlistPanel selectedTicker={selectedTicker} onSelect={onSelect} />
      </WatchlistProvider>
    </PricesProvider>,
  );
}

describe("watchlist panel", () => {
  it("renders live fields, selection and contract hooks", async () => {
    installDefaultApi();
    const onSelect = vi.fn();
    renderPanel({ onSelect });

    const row = await screen.findByTestId("watchlist-row-AAPL");
    expect(row).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveTextContent("$191.00");
    expect(screen.getByTestId("watchlist-change-AAPL")).toHaveTextContent("+0.53%");
    expect(screen.getByTestId("watchlist-sparkline-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("remove-ticker-AAPL")).toHaveAccessibleName(
      "Remove AAPL from watchlist",
    );

    await userEvent.click(screen.getByTestId("watchlist-row-NVDA"));
    expect(onSelect).toHaveBeenCalledWith("NVDA");
  });

  it("applies a streamed price and flashes the price cell", async () => {
    installDefaultApi();
    renderPanel();

    await screen.findByTestId("watchlist-row-AAPL");
    act(() =>
      MockEventSource.latest!.emitFrame({
        AAPL: {
          ticker: "AAPL",
          price: 192,
          previous_price: 191,
          timestamp: 1795102698,
          source: "simulator",
        },
      }),
    );

    const price = screen.getByTestId("watchlist-price-AAPL");
    expect(price).toHaveTextContent("$192.00");
    expect(price).toHaveAttribute("data-flash", "up");
  });

  it("validates a ticker client-side without a POST", async () => {
    const fetchMock = installDefaultApi();
    renderPanel();
    await screen.findByTestId("watchlist-row-AAPL");

    const input = screen.getByTestId("add-ticker-input");
    await userEvent.type(input, "1BAD");
    await userEvent.click(screen.getByTestId("add-ticker-submit"));

    expect(await screen.findByText(/Use 1–10 letters/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === "POST"),
    ).toBe(false);
  });

  it("surfaces the backend 409 detail on add", async () => {
    const fetchMock = installFetch((url, init) => {
      if (url.startsWith("/api/watchlist") && init?.method === "POST") {
        return jsonResponse({ detail: "PYPL is already in the watchlist" }, 409);
      }
      if (url.startsWith("/api/watchlist")) return jsonResponse(watchlistFixture);
      throw new Error(`Unhandled fetch: ${url}`);
    });
    renderPanel();
    await screen.findByTestId("watchlist-row-AAPL");

    await userEvent.type(screen.getByTestId("add-ticker-input"), "pypl");
    await userEvent.click(screen.getByTestId("add-ticker-submit"));

    expect(await screen.findByText("PYPL is already in the watchlist")).toBeInTheDocument();
    expect(screen.getByTestId("add-ticker-input")).toHaveValue("PYPL");
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post?.[1]?.body).toBe(JSON.stringify({ ticker: "PYPL" }));
  });

  it("removes a ticker after the DELETE succeeds", async () => {
    const fetchMock = installFetch((url, init) => {
      if (url.startsWith("/api/watchlist/") && init?.method === "DELETE") {
        return jsonResponse({ ticker: "AAPL", removed: true });
      }
      if (url.startsWith("/api/watchlist")) return jsonResponse(watchlistFixture);
      throw new Error(`Unhandled fetch: ${url}`);
    });
    renderPanel();
    await screen.findByTestId("watchlist-row-AAPL");

    await userEvent.click(screen.getByTestId("remove-ticker-AAPL"));

    await waitFor(() =>
      expect(screen.queryByTestId("watchlist-row-AAPL")).not.toBeInTheDocument(),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/watchlist/AAPL",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("shows an actionable empty state", async () => {
    installDefaultApi({ watchlist: { tickers: [] } });
    renderPanel({ selectedTicker: null });
    expect(await screen.findByText("Nothing on the watchlist")).toBeInTheDocument();
    expect(screen.getByTestId("add-ticker-input")).toBeInTheDocument();
  });

  it("does not collapse a load failure into the empty state", async () => {
    installFetch((url) => {
      if (url.startsWith("/api/watchlist")) {
        return jsonResponse({ detail: "Watchlist service unavailable" }, 503);
      }
      throw new Error(`Unhandled fetch: ${url}`);
    });
    renderPanel({ selectedTicker: null });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Watchlist service unavailable",
    );
    expect(screen.getByText("Watchlist unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Nothing on the watchlist")).not.toBeInTheDocument();
  });
});
