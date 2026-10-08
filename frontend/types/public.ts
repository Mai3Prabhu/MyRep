import { AgentIntent, EvidenceStatus, SourceDisplay, TurnSummary } from "./chat";

/**
 * Public professional representation (Layers 4 / 4.1).
 * Does not include contact preferences, timestamps, or indexing internals.
 */
export interface PublicProfile {
  id: string;
  name: string;
  headline: string | null;
  about: string | null;
  skills: unknown[] | null;
  experience: unknown[] | null;
  projects: unknown[] | null;
  education: unknown[] | null;
  knowledge_ready: boolean;
}

export interface PublicAskResponse {
  question: string;
  answer: string;
  sources: SourceDisplay[];
  evidence_status: EvidenceStatus;
  intent?: AgentIntent | null;
  contact_status?: string | null;
  summary?: TurnSummary | null;
}
