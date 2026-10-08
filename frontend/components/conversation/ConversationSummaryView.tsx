"use client";

import { forwardRef, useId, useState } from "react";
import RepAvatar, { RepState } from "@/components/brand/RepAvatar";
import { ConversationSummary } from "@/lib/conversationSummary";

/**
 * "What we've discussed" — the fairy's organized view of this session.
 *
 * Shows the visitor's questions and the names the Rep's answers mentioned.
 * It is a recap, not evidence: grounded claims live in the answers and their
 * sources. Session-only; nothing here is stored.
 */

const STATUS: Partial<Record<RepState, string>> = {
  listening: "Listening",
  capturing: "Noting your question…",
  thinking: "Looking through the profile…",
  organizing: "Organizing what we covered…",
  evidence_found: "Found supporting sources",
  speaking: "Answering",
};

function SummaryBody({ summary }: { summary: ConversationSummary }) {
  const fresh = new Set(summary.fresh.map((item) => item.toLowerCase()));
  if (summary.questions.length === 0) {
    return (
      <p className="mt-4 text-xs leading-relaxed text-[#8A8494]">
        Ask something and I&apos;ll keep track of it here.
      </p>
    );
  }
  return (
    <div className="mt-4 space-y-5">
      {summary.topics.length > 0 && (
        <p className="text-[11px] tracking-wide text-[#6D5A86]">{summary.topics.join("  ·  ")}</p>
      )}

      <section>
        <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A8494]">
          Asked
        </h3>
        <ul className="mt-2 space-y-1.5">
          {summary.questions.map((q) => (
            <li
              key={q.id}
              className={`flex gap-2 text-xs leading-snug ${
                fresh.has(q.id.toLowerCase()) ? "rep-fade-up" : ""
              } ${q.outcome === "not_in_profile" ? "text-[#8A8494]" : "text-[#3D3A45]"}`}
            >
              <span
                aria-hidden="true"
                className={`mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full ${
                  q.outcome === undefined
                    ? "bg-[#F0D56A]"
                    : q.outcome === "not_in_profile"
                    ? "bg-slate-300"
                    : "bg-[#B79AD6]"
                }`}
              />
              <span>
                {q.text}
                {q.outcome === "not_in_profile" && (
                  <span className="ml-1 whitespace-nowrap text-[10px] italic">· not in profile</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {summary.discussed.length > 0 && (
        <section>
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A8494]">
            Discussed
          </h3>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {summary.discussed.map((item) => (
              <li
                key={item}
                className={`rounded-full border border-[#E9D5FF] bg-white px-2.5 py-0.5 text-[11px] text-[#3D3A45] ${
                  fresh.has(item.toLowerCase()) ? "rep-chip-fresh" : ""
                }`}
              >
                {item}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

interface ViewProps {
  summary: ConversationSummary;
  repState: RepState;
  className?: string;
}

/** Desktop rail. The forwarded ref is where the fairy lands. */
export const ConversationRail = forwardRef<HTMLDivElement, ViewProps>(function ConversationRail(
  { summary, repState, className = "" },
  landingRef
) {
  const status = STATUS[repState];
  return (
    <aside
      aria-label="What we've discussed"
      className={`hidden w-64 shrink-0 overflow-y-auto border-l border-[#E6DFD4] bg-[#FBF8F4] px-5 py-6 lg:block ${className}`}
    >
      <div className="flex items-center gap-2.5">
        <div ref={landingRef} className="shrink-0">
          <RepAvatar size="sm" state={repState} interactive={false} />
        </div>
        <div className="min-w-0">
          <p className="font-display text-lg leading-none text-[#16161D]">What we&apos;ve discussed</p>
          <p className="mt-1 h-4 text-[11px] text-[#8A8494]" aria-live="polite">
            {status ?? ""}
          </p>
        </div>
      </div>
      <SummaryBody summary={summary} />
    </aside>
  );
});

/** Mobile: one quiet line that expands. The forwarded ref is the landing spot. */
export const ConversationPill = forwardRef<HTMLButtonElement, ViewProps>(function ConversationPill(
  { summary, repState, className = "" },
  landingRef
) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const count = summary.questions.length;
  // Appears as soon as the fairy starts capturing, so the first flight can land.
  if (count === 0 && (repState === "idle" || repState === "listening")) return null;
  return (
    <div className={`lg:hidden ${className}`}>
      {open && (
        <div
          id={panelId}
          className="rep-fade-up mb-2 max-h-[45vh] overflow-y-auto rounded-2xl border border-[#E6DFD4] bg-white/95 px-4 py-3 shadow-sm"
        >
          <SummaryBody summary={summary} />
        </div>
      )}
      <button
        ref={landingRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex items-center gap-2 rounded-full border border-[#E6DFD4] bg-white/80 py-1 pl-1 pr-3 text-[11px] text-[#5C5666]"
      >
        <RepAvatar size="xs" state={repState} interactive={false} />
        <span>
          What we&apos;ve discussed{count > 0 ? ` · ${count}` : ""}
        </span>
      </button>
    </div>
  );
});

/** The visible landing element (rail on desktop, pill on mobile). */
export function visibleTarget(...candidates: (HTMLElement | null)[]): HTMLElement | null {
  return candidates.find((el) => el !== null && el.offsetParent !== null) ?? null;
}
