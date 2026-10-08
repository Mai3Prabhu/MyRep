import { Profile, ProfileCreateInput, ProfileUpdateInput } from "@/types/profile";
import { DocumentItem } from "@/types/document";
import { DocumentIndexResponse, DocumentStatusItem, KnowledgeStatus } from "@/types/knowledge";
import { AskResponse, ConversationTurn } from "@/types/chat";
import { PublicAskResponse, PublicProfile } from "@/types/public";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`;
    try {
      const errorData = await response.json();
      if (typeof errorData.detail === "string") {
        errorMessage = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail
          .map((item: any) => item.msg || JSON.stringify(item))
          .join(", ");
      }
    } catch {
      // response body was not JSON, fallback to default message
    }
    throw new Error(errorMessage);
  }

  // 204 No Content has no body
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export async function getProfile(profileId: string): Promise<Profile> {
  const res = await fetch(`${API_BASE_URL}/api/v1/profiles/${profileId}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
  });
  return handleResponse<Profile>(res);
}

export async function findProfileByName(name: string): Promise<Profile | null> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/profiles/lookup?name=${encodeURIComponent(name)}`,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    }
  );
  if (res.status === 404) return null;
  return handleResponse<Profile>(res);
}

export async function createProfile(
  data: ProfileCreateInput
): Promise<Profile> {
  const res = await fetch(`${API_BASE_URL}/api/v1/profiles/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(data),
  });
  return handleResponse<Profile>(res);
}

export async function updateProfile(
  profileId: string,
  data: ProfileUpdateInput
): Promise<Profile> {
  const res = await fetch(`${API_BASE_URL}/api/v1/profiles/${profileId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(data),
  });
  return handleResponse<Profile>(res);
}

export async function listDocuments(
  profileId: string
): Promise<DocumentItem[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/profiles/${profileId}/documents`,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    }
  );
  return handleResponse<DocumentItem[]>(res);
}

export async function uploadDocument(
  profileId: string,
  file: File
): Promise<DocumentItem> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(
    `${API_BASE_URL}/api/v1/profiles/${profileId}/documents`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
      body: formData,
    }
  );
  return handleResponse<DocumentItem>(res);
}

export async function getDocument(documentId: string): Promise<DocumentItem> {
  const res = await fetch(`${API_BASE_URL}/api/v1/documents/${documentId}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
  });
  return handleResponse<DocumentItem>(res);
}

// ---------------------------------------------------------------------------
// Layer 2.9 / Layer 3 — Knowledge status + document indexing
// ---------------------------------------------------------------------------

export async function getKnowledgeStatus(
  profileId: string
): Promise<KnowledgeStatus> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/profiles/${profileId}/knowledge-status`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
    }
  );
  return handleResponse<KnowledgeStatus>(res);
}

export async function getDocumentStatuses(
  profileId: string
): Promise<DocumentStatusItem[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/profiles/${profileId}/documents/status`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
    }
  );
  return handleResponse<DocumentStatusItem[]>(res);
}

export async function indexDocument(
  documentId: string
): Promise<DocumentIndexResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/documents/${documentId}/index`,
    {
      method: "POST",
      headers: { Accept: "application/json" },
    }
  );
  return handleResponse<DocumentIndexResponse>(res);
}

// ---------------------------------------------------------------------------
// Layer 3.5 / 3.6 — MyRep chat with optional session history
// ---------------------------------------------------------------------------

/**
 * Maximum number of recent turns to send as conversation context.
 * Must match or stay under the backend MAX_CONVERSATION_MESSAGES setting (default 10).
 */
const MAX_HISTORY_TO_SEND = 10;

export async function askMyRep(
  profileId: string,
  question: string,
  conversationHistory: ConversationTurn[] = []
): Promise<AskResponse> {
  // Only send the most recent turns to stay within the backend limit.
  const boundedHistory = conversationHistory.slice(-MAX_HISTORY_TO_SEND);

  const body: { question: string; conversation_history?: ConversationTurn[] } =
    { question };
  if (boundedHistory.length > 0) {
    body.conversation_history = boundedHistory;
  }

  const res = await fetch(
    `${API_BASE_URL}/api/v1/profiles/${profileId}/ask`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    }
  );
  return handleResponse<AskResponse>(res);
}

// ---------------------------------------------------------------------------
// Layer 4 / 4.1 — Public recruiter view (separate security boundary)
// ---------------------------------------------------------------------------

export async function getPublicProfile(
  profileId: string
): Promise<PublicProfile> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/public/profiles/${profileId}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
    }
  );
  return handleResponse<PublicProfile>(res);
}

export async function askPublicMyRep(
  profileId: string,
  question: string,
  conversationHistory: ConversationTurn[] = []
): Promise<PublicAskResponse> {
  const boundedHistory = conversationHistory.slice(-MAX_HISTORY_TO_SEND);

  const body: { question: string; conversation_history?: ConversationTurn[] } =
    { question };
  if (boundedHistory.length > 0) {
    body.conversation_history = boundedHistory;
  }

  const res = await fetch(
    `${API_BASE_URL}/api/v1/public/profiles/${profileId}/ask`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    }
  );
  return handleResponse<PublicAskResponse>(res);
}

export function voiceLiveUrl(
  profileId: string,
  visibility: "public" | "private"
): string {
  const httpBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  const wsBase = httpBase.replace(/^http/, "ws");
  if (visibility === "public") {
    return `${wsBase}/api/v1/public/profiles/${profileId}/voice/live`;
  }
  return `${wsBase}/api/v1/voice/profiles/${profileId}/live`;
}
