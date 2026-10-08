"use client";

import { ReactNode, useCallback, useRef, useState } from "react";
import Link from "next/link";
import {
  AgentIntent,
  ChatMessage,
  ConversationTurn,
  EvidenceStatus,
  SourceDisplay,
  TurnSummary,
} from "@/types/chat";
import { shouldShowEvidence } from "@/lib/conversationSummary";
import ChatWindow from "./ChatWindow";
import ChatInput from "./ChatInput";
import RepNavbar from "../brand/RepNavbar";
import {
  ConversationPill,
  ConversationRail,
} from "../conversation/ConversationSummaryView";
import { useConversationFairy } from "../conversation/useConversationFairy";

const MAX_MESSAGES_IN_MEMORY = 100;

function newId(): string {
  return crypto.randomUUID();
}

export interface AskResult {
  answer: string;
  sources: SourceDisplay[];
  evidence_status: EvidenceStatus;
  intent?: AgentIntent | null;
  contact_status?: string | null;
  summary?: TurnSummary | null;
}

interface ChatPanelProps {
  title: string;
  subtitle?: string;
  backHref: string;
  backLabel: string;
  askFn: (question: string, history: ConversationTurn[]) => Promise<AskResult>;
  knowledgeReady: boolean | null;
  knowledgeWarning?: ReactNode;
  disabled?: boolean;
  disabledReason?: string;
  blockWhenNotReady?: boolean;
  voiceHref?: string;
  activeChatHref?: string;
}

export default function ChatPanel({
  title,
  subtitle,
  backHref,
  backLabel,
  askFn,
  knowledgeReady,
  knowledgeWarning,
  disabled,
  disabledReason,
  blockWhenNotReady = false,
  voiceHref,
  activeChatHref,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const lastUserQuestion = useRef<string>("");
  const {
    summary,
    repState: fairyState,
    railRef,
    pillRef,
    flightLayer,
    capture,
    organize,
    settle,
  } = useConversationFairy(loading ? "thinking" : "idle");

  const chatDisabled =
    Boolean(disabled) || (blockWhenNotReady && knowledgeReady === false);

  const sendQuestion = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || loading || chatDisabled) return;

      lastUserQuestion.current = trimmed;

      const historyToSend: ConversationTurn[] = messages
        .filter((m) => !m.error)
        .map((m) => ({ role: m.role, content: m.content }));

      const userMsg: ChatMessage = {
        id: newId(),
        role: "user",
        content: trimmed,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg].slice(-MAX_MESSAGES_IN_MEMORY));
      setInput("");
      setLoading(true);
      // One capture per submitted turn: the fairy carries the question to the summary.
      void capture(userMsg.id, trimmed, () =>
        document.querySelector(`[data-message-id="${userMsg.id}"]`)
      );

      try {
        const response = await askFn(trimmed, historyToSend);
        const assistantMsg: ChatMessage = {
          id: newId(),
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          evidenceStatus: response.evidence_status,
          intent: response.intent,
          contactStatus: response.contact_status,
          summary: response.summary,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) =>
          [...prev, assistantMsg].slice(-MAX_MESSAGES_IN_MEMORY)
        );
        organize(
          userMsg.id,
          response.summary,
          shouldShowEvidence(response.sources.length, response.summary, response.intent)
        );
      } catch {
        settle();
        const errorMsg: ChatMessage = {
          id: newId(),
          role: "assistant",
          content: "I couldn't answer that right now. Please try again.",
          timestamp: new Date().toISOString(),
          error: true,
        };
        setMessages((prev) =>
          [...prev, errorMsg].slice(-MAX_MESSAGES_IN_MEMORY)
        );
      } finally {
        setLoading(false);
      }
    },
    [messages, loading, chatDisabled, askFn, capture, organize, settle]
  );

  const handleRetry = useCallback(
    (errorMsgId: string) => {
      setMessages((prev) => prev.filter((m) => m.id !== errorMsgId));
      sendQuestion(lastUserQuestion.current);
    },
    [sendQuestion]
  );

  return (
    <div className="flex h-dvh flex-col bg-[#FBF8F4]">
      <RepNavbar chatHref={activeChatHref} profileHref={backHref} />

      {/* Warnings & Reason Banners */}
      {disabledReason && (
        <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-xs font-medium text-red-700">
          {disabledReason}
        </div>
      )}

      {knowledgeReady === false && knowledgeWarning}

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Chat Messages Canvas */}
          <ChatWindow
            messages={messages}
            loading={loading}
            onSuggest={sendQuestion}
            onRetry={handleRetry}
            suggestionsEnabled={!chatDisabled}
            personName={title.replace(/Talk to |'s Professional Representative|'s AI Representative/gi, "").trim()}
          />

          {/* Input area */}
          <div className="border-t border-[#E6DFD4] bg-[#FBF8F4] px-4 py-4">
            <div className="mx-auto max-w-2xl">
              <ConversationPill
                ref={pillRef}
                summary={summary}
                repState={fairyState}
                className="mb-3"
              />
              <div className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <ChatInput
                    value={input}
                    onChange={setInput}
                    onSend={() => sendQuestion(input)}
                    loading={loading}
                    disabled={chatDisabled}
                  />
                </div>
                {voiceHref && (
                  <Link
                    href={voiceHref}
                    aria-label="Voice"
                    title="Voice"
                    className="mb-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#16161D]"
                  >
                    🎙
                  </Link>
                )}
              </div>
            </div>
          </div>
        </div>

        <ConversationRail ref={railRef} summary={summary} repState={fairyState} />
      </div>

      {flightLayer}
    </div>
  );
}
