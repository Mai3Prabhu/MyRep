"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatMessage as ChatMessageType } from "@/types/chat";
import { shouldShowEvidence } from "@/lib/conversationSummary";
import SourceReferences from "./SourceReferences";
import RepAvatar from "@/components/brand/RepAvatar";

interface Props {
  message: ChatMessageType;
  onRetry?: () => void;
}

function EvidencePill({
  status,
  intent,
}: {
  status: ChatMessageType["evidenceStatus"];
  intent?: ChatMessageType["intent"];
}) {
  if (intent && intent !== "knowledge") return null;
  if (!status || status === "evidence_available") return null;

  const label =
    status === "no_evidence"
      ? "⚠ No matching evidence found in verified documents"
      : "ℹ Limited matching evidence in verified documents";

  return (
    <div className="mt-2.5 inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-semibold text-amber-700 border border-amber-200/80">
      <span>{label}</span>
    </div>
  );
}

function ContactStatusNote({ status }: { status?: string | null }) {
  if (!status || status === "none") return null;
  const label =
    status === "pending"
      ? "✓ Contact request recorded (pending delivery)"
      : status === "failed"
      ? "✕ Contact request could not be recorded"
      : status === "offered"
      ? "Public contact info is available if you'd like to reach out directly"
      : null;
  if (!label) return null;
  return (
    <p className="mt-2 text-[11px] font-medium text-slate-500 italic" role="note">
      {label}
    </p>
  );
}

export default function ChatMessage({ message, onRetry }: Props) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div
          data-message-id={message.id}
          className="max-w-[82%] sm:max-w-[70%] rounded-3xl rounded-tr-xs bg-slate-900 px-5 py-3 text-xs sm:text-sm text-white shadow-sm leading-relaxed"
          role="log"
          aria-label="Your message"
        >
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
      </div>
    );
  }

  // Assistant message error
  if (message.error) {
    return (
      <div className="flex items-start gap-3 justify-start">
        <RepAvatar size="sm" state="idle" interactive={false} still />
        <div
          className="max-w-[85%] rounded-3xl rounded-tl-xs border border-red-200 bg-red-50/90 px-5 py-3.5 text-xs sm:text-sm shadow-xs"
          role="alert"
        >
          <p className="font-semibold text-red-700">{message.content}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-2 text-xs font-semibold text-red-600 underline underline-offset-2 hover:text-red-800"
            >
              Try again
            </button>
          )}
        </div>
      </div>
    );
  }

  // Assistant response
  return (
    <div className="flex items-start gap-3 justify-start">
      <div className="shrink-0 mt-0.5">
        <RepAvatar size="sm" state="idle" interactive={false} still />
      </div>

      <div
        className="max-w-[88%] sm:max-w-[80%] rounded-3xl rounded-tl-xs border border-rep-lavender-200/90 bg-white px-5 py-4 text-xs sm:text-sm text-slate-800 shadow-sm"
        role="log"
        aria-label="MyRep response"
      >
        <div className="prose prose-sm max-w-none text-xs sm:text-sm leading-relaxed prose-p:my-1.5 prose-ul:my-1 prose-li:my-0.5 prose-headings:text-slate-900 prose-strong:text-slate-900">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        </div>

        <EvidencePill status={message.evidenceStatus} intent={message.intent} />
        <ContactStatusNote status={message.contactStatus} />

        {message.sources &&
          shouldShowEvidence(message.sources.length, message.summary, message.intent) && (
            <SourceReferences sources={message.sources} />
          )}
      </div>
    </div>
  );
}
