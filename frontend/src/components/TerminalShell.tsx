"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AppHeader } from "./AppHeader";
import { ChatPanel } from "./ChatPanel";
import { MainChart } from "./MainChart";
import { MobileTabBar, type MobileTab } from "./MobileTabBar";
import { PortfolioPanel } from "./PortfolioPanel";
import { TradeBar } from "./TradeBar";
import { WatchlistPanel } from "./WatchlistPanel";
import { ChatProvider } from "@/providers/ChatProvider";
import { PortfolioProvider } from "@/providers/PortfolioProvider";
import { PricesProvider } from "@/providers/PricesProvider";
import { WatchlistProvider, useWatchlist } from "@/providers/WatchlistProvider";

function TerminalWorkspace() {
  const { tickers } = useWatchlist();
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [mobileTab, setMobileTab] = useState<MobileTab>("watchlist");
  const [chatOpen, setChatOpen] = useState(false);
  const chatToggleRef = useRef<HTMLButtonElement | null>(null);

  // Initial selection is the first watchlist ticker; if that row is removed,
  // fall back to the new first row instead of charting a ghost.
  useEffect(() => {
    if (tickers.length === 0) {
      if (selectedTicker !== null) setSelectedTicker(null);
      return;
    }
    if (!selectedTicker || !tickers.some((entry) => entry.ticker === selectedTicker)) {
      setSelectedTicker(tickers[0].ticker);
    }
  }, [tickers, selectedTicker]);

  const closeChat = useCallback(() => {
    setChatOpen(false);
    window.setTimeout(() => chatToggleRef.current?.focus(), 0);
  }, []);

  const toggleChat = useCallback(() => {
    if (chatOpen) {
      closeChat();
      return;
    }
    setChatOpen(true);
    window.setTimeout(() => document.getElementById("chat-input")?.focus(), 0);
  }, [chatOpen, closeChat]);

  useEffect(() => {
    if (!chatOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeChat();
        return;
      }
      if (event.key !== "Tab") return;

      // The tablet drawer covers the workspace; keep keyboard focus inside it
      // until it closes, then return focus to the header trigger.
      const panel = document.getElementById("chat-panel");
      const container = panel?.closest(".chat-col");
      if (!container) return;
      const focusable = Array.from(
        container.querySelectorAll<HTMLElement>(
          'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), a[href]',
        ),
      ).filter((element) => element.getClientRects().length > 0);
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      const inside = active instanceof Node && container.contains(active);

      if (event.shiftKey && (active === first || !inside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !inside)) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [chatOpen, closeChat]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <h1 className="sr-only">FinAlly trading workstation</h1>

      <AppHeader
        chatOpen={chatOpen}
        onToggleChat={toggleChat}
        chatToggleRef={chatToggleRef}
      />

      <div className="app-body">
        <aside
          className="left-col"
          data-mobile-active={mobileTab === "watchlist"}
          aria-label="Watchlist and order entry"
        >
          <WatchlistPanel
            selectedTicker={selectedTicker}
            onSelect={setSelectedTicker}
          />
          <TradeBar selectedTicker={selectedTicker} />
        </aside>

        <main
          className="center-col"
          id="main-content"
          data-mobile-active={mobileTab === "chart" || mobileTab === "portfolio"}
          data-mobile-view={mobileTab}
        >
          <MainChart selectedTicker={selectedTicker} />
          <PortfolioPanel />
        </main>

        <aside
          className="chat-col"
          data-open={chatOpen}
          data-mobile-active={mobileTab === "chat"}
          aria-label="AI assistant"
        >
          <ChatPanel onRequestClose={closeChat} />
        </aside>

        <div
          className="drawer-backdrop"
          data-open={chatOpen}
          aria-hidden="true"
          onClick={closeChat}
        />
      </div>

      <MobileTabBar active={mobileTab} onChange={setMobileTab} />
    </div>
  );
}

export function TerminalShell() {
  return (
    <PricesProvider>
      <PortfolioProvider>
        <WatchlistProvider>
          <ChatProvider>
            <TerminalWorkspace />
          </ChatProvider>
        </WatchlistProvider>
      </PortfolioProvider>
    </PricesProvider>
  );
}
