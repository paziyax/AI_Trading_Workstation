"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { postChat, toErrorMessage } from "@/lib/api";
import { makeId } from "@/lib/id";
import type { ChatMessage, ChatResponse } from "@/lib/types";

const GREETING: ChatMessage = {
  id: "greeting",
  role: "assistant",
  content:
    "I’m FinAlly, your trading assistant. Ask about your portfolio, or tell me to buy, sell or watch a ticker.",
};

export interface ChatContextValue {
  messages: ChatMessage[];
  pending: boolean;
  error: string | null;
  send: (message: string) => Promise<ChatResponse | null>;
  clearError: () => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingRef = useRef(false);

  const send = useCallback(async (raw: string): Promise<ChatResponse | null> => {
    const message = raw.trim();
    if (!message || pendingRef.current) return null;

    pendingRef.current = true;
    setPending(true);
    setError(null);
    setMessages((current) => [
      ...current,
      { id: makeId("user"), role: "user", content: message, createdAt: Date.now() },
    ]);

    try {
      const response = await postChat(message);
      setMessages((current) => [
        ...current,
        {
          id: makeId("assistant"),
          role: "assistant",
          content: response.message,
          actions: response.actions,
          createdAt: Date.now(),
        },
      ]);
      return response;
    } catch (cause) {
      setError(toErrorMessage(cause));
      return null;
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  const value = useMemo<ChatContextValue>(
    () => ({ messages, pending, error, send, clearError }),
    [messages, pending, error, send, clearError],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatContextValue {
  const context = useContext(ChatContext);
  if (!context) throw new Error("useChat must be used inside ChatProvider");
  return context;
}
