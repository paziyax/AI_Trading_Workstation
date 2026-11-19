"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { chatActionChips } from "@/lib/chat";
import { formatUpdateTime } from "@/lib/format";
import type { ChatMessage } from "@/lib/types";
import { useChat } from "@/providers/ChatProvider";
import { usePortfolio } from "@/providers/PortfolioProvider";
import { useWatchlist } from "@/providers/WatchlistProvider";

function MessageBubble({ message }: { message: ChatMessage }) {
  const chips = chatActionChips(message.actions);

  return (
    <article
      className={`chat-message chat-message-${message.role}`}
      data-testid={`chat-message-${message.role === "user" ? "user" : "assistant"}`}
    >
      <div className="chat-meta">
        <span className="chat-author">{message.role === "user" ? "You" : "FinAlly"}</span>
        {message.createdAt ? (
          <span className="chat-time mono">{formatUpdateTime(message.createdAt)}</span>
        ) : null}
      </div>
      <p className="chat-body">{message.content}</p>
      {chips.length > 0 ? (
        <div className="chat-actions" data-testid="chat-actions" aria-label="Actions taken">
          {chips.map((chip) => (
            <span
              key={chip.key}
              className={`action-chip is-${chip.status}`}
              title={chip.detail}
            >
              <span className="action-chip-label">{chip.label}</span>
              {chip.detail ? (
                <span className="action-chip-detail mono">{chip.detail}</span>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function ChatPanel({ onRequestClose }: { onRequestClose: () => void }) {
  const { messages, pending, error, send, clearError } = useChat();
  const { applyPortfolio, refreshHistory } = usePortfolio();
  const { refresh: refreshWatchlist } = useWatchlist();
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, pending]);

  const submit = async () => {
    const text = draft.trim();
    if (!text || pending) return;
    const response = await send(text);
    if (!response) return;
    setDraft("");
    applyPortfolio(response.portfolio);
    void refreshHistory();
    void refreshWatchlist();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <section
      className="panel chat-panel"
      data-testid="chat-panel"
      id="chat-panel"
      aria-labelledby="chat-title"
    >
      <div className="panel-header chat-head">
        <div className="chat-title-wrap">
          <h2 className="panel-label" id="chat-title">
            AI Assistant
          </h2>
          <span className="chat-subtitle">Portfolio-aware</span>
        </div>
        <button
          type="button"
          className="chat-close"
          aria-label="Close AI assistant"
          onClick={onRequestClose}
        >
          ×
        </button>
      </div>

      {error ? (
        <div className="panel-banner">
          <div className="inline-error is-compact" role="alert" data-testid="chat-error">
            <span className="inline-error-mark" aria-hidden="true">
              !
            </span>
            <span className="inline-error-text">{error}</span>
            <button
              type="button"
              className="inline-error-dismiss"
              aria-label="Dismiss error"
              onClick={clearError}
            >
              ×
            </button>
          </div>
        </div>
      ) : null}

      <div className="chat-scroll" role="log" aria-live="polite" aria-relevant="additions">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {pending ? (
          <div className="chat-message chat-message-assistant chat-loading-row" data-testid="chat-loading" role="status">
            <div className="chat-meta">
              <span className="chat-author">FinAlly</span>
            </div>
            <div className="chat-loading">
              <span className="loading-dot" aria-hidden="true" />
              <span className="loading-dot" aria-hidden="true" />
              <span className="loading-dot" aria-hidden="true" />
              <span className="loading-label">Reading your portfolio…</span>
            </div>
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>

      <form className="composer" onSubmit={handleSubmit}>
        <div className="composer-head">
          <label className="field-label" htmlFor="chat-input">
            Ask the assistant
          </label>
          <span className="composer-hint">Enter sends, Shift+Enter adds a line</span>
        </div>
        <textarea
          id="chat-input"
          data-testid="chat-input"
          className="composer-input"
          rows={2}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Buy 5 AAPL, or review my concentration risk"
          maxLength={2000}
          disabled={pending}
        />
        <div className="composer-actions">
          <span className="composer-count mono">{draft.length}/2000</span>
          <button
            type="submit"
            className="btn btn-secondary composer-send"
            data-testid="chat-send"
            disabled={pending || !draft.trim()}
            aria-busy={pending}
          >
            Send
          </button>
        </div>
      </form>
    </section>
  );
}
