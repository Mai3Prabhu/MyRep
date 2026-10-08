/**
 * Types for the MyRep chat UI (Layers 3.5 / 3.6).
 *
 * ChatMessage  — frontend-only in-memory conversation state.
 * ConversationTurn — shape sent to the backend for follow-up context.
 * AskResponse  — shape returned by POST /api/v1/profiles/{id}/ask.
 */

export type EvidenceStatus =
  | "no_evidence"
  | "weak_evidence"
  | "evidence_available";

/** Safe provenance shown under an answer. Public responses include only filename + page. */
export interface SourceDisplay {
  filename: string;
  page_number: number;
  /** Private responses only: a short verbatim quote from the consulted chunk. */
  excerpt?: string | null;
}

export type TurnOutcome = "answered" | "not_in_profile" | "contact" | "declined";

/**
 * Deterministic digest of one completed turn, built by the backend from the
 * question, the Rep's answer, and names in public profile fields.
 * Display only — never sent back to the backend, never authoritative.
 */
export interface TurnSummary {
  question: string;
  topics: string[];
  entities: string[];
  technologies: string[];
  key_points: string[];
  outcome: TurnOutcome;
}

export interface SourceReference extends SourceDisplay {
  document_id?: string;
  chunk_index?: number;
  score?: number | null;
}

/** Minimal turn shape sent to the backend — no UI-specific fields. */
export interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

export type AgentIntent = "knowledge" | "contact" | "unsupported";

export interface AskResponse {
  question: string;
  answer: string;
  sources: SourceReference[];
  evidence_status: EvidenceStatus;
  intent?: AgentIntent | null;
  contact_status?: string | null;
  summary?: TurnSummary | null;
}

/**
 * Full in-memory chat message with UI state.
 * Never persisted to MySQL, localStorage, or Qdrant.
 */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceDisplay[];
  evidenceStatus?: EvidenceStatus;
  intent?: AgentIntent | null;
  contactStatus?: string | null;
  summary?: TurnSummary | null;
  timestamp: string;
  /** True when the backend call failed — shows retry UI in the message bubble. */
  error?: boolean;
}
