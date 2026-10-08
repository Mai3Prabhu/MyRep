/**
 * Session-level "What we've discussed" state.
 *
 * Built only from:
 *   - the visitor's own question (captured when the turn starts), and
 *   - the backend's deterministic per-turn digest (TurnSummary).
 *
 * Lives in React state for the current page session. Never persisted, never
 * sent back to the backend, never used as evidence.
 */

import { TurnOutcome, TurnSummary } from "@/types/chat";

const MAX_QUESTIONS = 6;
const MAX_TOPICS = 5;
const MAX_DISCUSSED = 12;

export interface DiscussedQuestion {
  /** The turn this question started (chat message id or voice turn id). */
  id: string;
  text: string;
  /** Undefined until the Rep has answered. */
  outcome?: TurnOutcome;
}

export interface ConversationSummary {
  questions: DiscussedQuestion[];
  topics: string[];
  /** Projects, organisations and technologies the Rep's answers mentioned. */
  discussed: string[];
  /** Items added by the most recent update — the UI highlights these. */
  fresh: string[];
}

export const EMPTY_SUMMARY: ConversationSummary = {
  questions: [],
  topics: [],
  discussed: [],
  fresh: [],
};

function shorten(text: string, limit = 80): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= limit) return clean;
  return `${clean.slice(0, limit - 1).replace(/\s+\S*$/, "")}…`;
}

function mergeUnique(existing: string[], incoming: string[], cap: number) {
  const seen = new Set(existing.map((item) => item.toLowerCase()));
  const added: string[] = [];
  for (const item of incoming) {
    const key = item.toLowerCase();
    if (!item.trim() || seen.has(key)) continue;
    seen.add(key);
    added.push(item);
  }
  return { merged: [...existing, ...added].slice(-cap), added };
}

/** The fairy has picked up a question: list it under "Asked". */
export function captureQuestion(
  summary: ConversationSummary,
  id: string,
  text: string
): ConversationSummary {
  if (summary.questions.some((q) => q.id === id)) return summary;
  // A repeated question is a legitimate new turn; show it once, most recent last.
  const others = summary.questions.filter(
    (q) => q.text.toLowerCase() !== shorten(text).toLowerCase()
  );
  return {
    ...summary,
    questions: [...others, { id, text: shorten(text) }].slice(-MAX_QUESTIONS),
    fresh: [id],
  };
}

/** The Rep answered: organise the turn's digest into the summary. */
export function applyTurnSummary(
  summary: ConversationSummary,
  id: string,
  digest: TurnSummary | null | undefined
): ConversationSummary {
  if (!digest) {
    return { ...summary, fresh: [] };
  }
  const questions = summary.questions.some((q) => q.id === id)
    ? summary.questions.map((q) => (q.id === id ? { ...q, outcome: digest.outcome } : q))
    : [...summary.questions, { id, text: shorten(digest.question), outcome: digest.outcome }].slice(
        -MAX_QUESTIONS
      );
  const topics = mergeUnique(
    summary.topics,
    digest.topics.filter((t) => t !== "General"),
    MAX_TOPICS
  );
  const discussed = mergeUnique(
    summary.discussed,
    [...digest.entities, ...digest.technologies],
    MAX_DISCUSSED
  );
  return {
    questions,
    topics: topics.merged,
    discussed: discussed.merged,
    fresh: [...topics.added, ...discussed.added],
  };
}

/** Evidence is shown only for answers the Rep actually grounded. */
export function shouldShowEvidence(
  sourcesCount: number,
  digest: TurnSummary | null | undefined,
  intent?: string | null
): boolean {
  if (sourcesCount === 0) return false;
  if (intent && intent !== "knowledge") return false;
  if (digest && digest.outcome !== "answered") return false;
  return true;
}
