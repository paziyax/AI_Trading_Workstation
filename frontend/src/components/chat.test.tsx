import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ChatPanel } from "@/components/ChatPanel";
import {
  historyFixture,
  installFetch,
  jsonResponse,
  portfolioFixture,
  watchlistFixture,
} from "@/test/fixtures";
import { ChatProvider } from "@/providers/ChatProvider";
import { PortfolioProvider } from "@/providers/PortfolioProvider";
import { PricesProvider } from "@/providers/PricesProvider";
import { WatchlistProvider } from "@/providers/WatchlistProvider";

function renderChat() {
  return render(
    <PricesProvider>
      <PortfolioProvider>
        <WatchlistProvider>
          <ChatProvider>
            <ChatPanel onRequestClose={() => {}} />
          </ChatProvider>
        </WatchlistProvider>
      </PortfolioProvider>
    </PricesProvider>,
  );
}

const chatResponse = {
  message: "Bought 5 AAPL at $191.00. PYPL is now on the watchlist.",
  actions: {
    trades: [
      {
        ticker: "AAPL",
        side: "buy",
        quantity: 5,
        status: "executed",
        price: 191,
        error: null,
      },
      {
        ticker: "NVDA",
        side: "buy",
        quantity: 10,
        status: "failed",
        price: null,
        error: "Insufficient cash",
      },
    ],
    watchlist_changes: [
      { ticker: "PYPL", action: "add", status: "executed", error: null },
    ],
  },
  portfolio: portfolioFixture,
};

function baseRouting(url: string) {
  if (url.startsWith("/api/portfolio/history")) return jsonResponse(historyFixture);
  if (url.startsWith("/api/portfolio")) return jsonResponse(portfolioFixture);
  if (url.startsWith("/api/watchlist")) return jsonResponse(watchlistFixture);
  throw new Error(`Unhandled fetch: ${url}`);
}

describe("chat panel", () => {
  it("shows the greeting and a loading state while the assistant thinks", async () => {
    let resolveChat: ((response: Response) => void) | undefined;
    const pendingChat = new Promise<Response>((resolve) => {
      resolveChat = resolve;
    });
    installFetch((url, init) => {
      if (url === "/api/chat" && init?.method === "POST") return pendingChat;
      return baseRouting(url);
    });

    renderChat();
    expect(screen.getByTestId("chat-message-assistant")).toHaveTextContent("FinAlly");

    await userEvent.type(screen.getByTestId("chat-input"), "Buy 5 AAPL and add PYPL");
    await userEvent.click(screen.getByTestId("chat-send"));

    expect(screen.getByTestId("chat-message-user")).toHaveTextContent(
      "Buy 5 AAPL and add PYPL",
    );
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
    expect(screen.getByTestId("chat-input")).toBeDisabled();

    await act(async () => {
      resolveChat?.(jsonResponse(chatResponse));
      await Promise.resolve();
    });

    expect(
      await screen.findByText("Bought 5 AAPL at $191.00. PYPL is now on the watchlist."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("chat-loading")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("chat-input")).toBeEnabled());
  });

  it("appends the assistant reply and one chip per executed or failed action", async () => {
    installFetch((url, init) => {
      if (url === "/api/chat" && init?.method === "POST") {
        return jsonResponse(chatResponse);
      }
      return baseRouting(url);
    });

    renderChat();
    await userEvent.type(screen.getByTestId("chat-input"), "Buy 5 AAPL and add PYPL");
    await userEvent.click(screen.getByTestId("chat-send"));

    expect(
      await screen.findByText("Bought 5 AAPL at $191.00. PYPL is now on the watchlist."),
    ).toBeInTheDocument();

    const actions = screen.getByTestId("chat-actions");
    expect(actions).toHaveTextContent("Bought 5 AAPL");
    expect(actions).toHaveTextContent("Added PYPL");
    expect(actions).toHaveTextContent("Failed: Insufficient cash");
    expect(actions.querySelectorAll(".action-chip")).toHaveLength(3);
    expect(actions.querySelectorAll(".action-chip.is-failed")).toHaveLength(1);

    expect(screen.getByTestId("chat-input")).toBeEnabled();
    expect(screen.getByTestId("chat-input")).toHaveValue("");
    expect(screen.getAllByTestId("chat-message-assistant")).toHaveLength(2);
  });

  it("surfaces a 503 as chat-error and keeps the typed message", async () => {
    installFetch((url, init) => {
      if (url === "/api/chat" && init?.method === "POST") {
        return jsonResponse(
          { detail: "AI assistant unavailable: model offline" },
          503,
        );
      }
      return baseRouting(url);
    });

    renderChat();
    await userEvent.type(screen.getByTestId("chat-input"), "Review my risk");
    await userEvent.click(screen.getByTestId("chat-send"));

    expect(await screen.findByTestId("chat-error")).toHaveTextContent(
      "AI assistant unavailable: model offline",
    );
    expect(screen.getByTestId("chat-input")).toHaveValue("Review my risk");
    expect(screen.getByTestId("chat-input")).toBeEnabled();
    expect(screen.queryByTestId("chat-loading")).not.toBeInTheDocument();
  });
});
