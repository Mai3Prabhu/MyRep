"use client";

import { useEffect, useRef } from "react";
import { ChatMessage as ChatMessageType } from "@/types/chat";
import ChatMessage from "./ChatMessage";
import SuggestedQuestions from "./SuggestedQuestions";
import RepAvatar from "../brand/RepAvatar";

interface Props {
  messages: ChatMessageType[];
  loading: boolean;
  onSuggest: (question: string) => void;
  onRetry: (failedMsgId: string) => void;
  suggestionsEnabled?: boolean;
  personName?: string;
}

export default function ChatWindow({
  messages,
  loading,
  onSuggest,
  onRetry,
  suggestionsEnabled = true,
  personName,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const isEmpty = messages.length === 0 && !loading;

  return (
    <div
      className="flex-1 overflow-y-auto px-4 py-6"
      aria-live="polite"
      aria-label="Conversation"
    >
      <div className="mx-auto max-w-3xl">
        {isEmpty ? (
          suggestionsEnabled ? (
            <SuggestedQuestions onSelect={onSuggest} personName={personName} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center py-16 text-center text-xs text-slate-500">
              <RepAvatar size="md" state="idle" />
              <p className="mt-3">MyRep isn&apos;t ready to answer questions yet.</p>
            </div>
          )
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onRetry={msg.error ? () => onRetry(msg.id) : undefined}
              />
            ))}

            {loading && (
              <div className="flex items-center gap-3 justify-start" aria-label="Rep is thinking">
                <RepAvatar size="sm" state="thinking" interactive={false} />
                <div className="flex items-center gap-2 rounded-3xl rounded-tl-xs border border-rep-lavender-200 bg-white px-4 py-3 text-xs font-medium text-slate-600 shadow-2xs">
                  <span className="inline-flex gap-1" aria-hidden="true">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal-500 [animation-delay:-0.3s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-rep-lavender-500 [animation-delay:-0.15s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-amber-400" />
                  </span>
                  <span>Rep is thinking</span>
                </div>
              </div>
            )}

            <div ref={bottomRef} aria-hidden="true" />
          </div>
        )}
      </div>
    </div>
  );
}
