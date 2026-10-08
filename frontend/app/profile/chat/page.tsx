"use client";

import { useCallback, useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { ConversationTurn } from "@/types/chat";
import { Profile } from "@/types/profile";
import { askMyRep, getKnowledgeStatus, getProfile } from "@/lib/api";
import ChatPanel from "@/components/chat/ChatPanel";

function PrivateChatView() {
  const searchParams = useSearchParams();
  const profileId = searchParams.get("id") || "";

  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [knowledgeReady, setKnowledgeReady] = useState<boolean | null>(null);

  useEffect(() => {
    if (!profileId) return;

    getProfile(profileId)
      .then(setProfile)
      .catch((err: unknown) => {
        setProfileError(
          err instanceof Error ? err.message : "Profile not found."
        );
      });

    getKnowledgeStatus(profileId)
      .then((status) => setKnowledgeReady(status.rag_ready))
      .catch(() => setKnowledgeReady(null));
  }, [profileId]);

  const askFn = useCallback(
    async (question: string, history: ConversationTurn[]) => {
      const response = await askMyRep(profileId, question, history);
      return {
        answer: response.answer,
        sources: response.sources,
        evidence_status: response.evidence_status,
        intent: response.intent,
        contact_status: response.contact_status,
        summary: response.summary,
      };
    },
    [profileId]
  );

  if (!profileId) {
    return (
      <div className="flex h-dvh items-center justify-center px-4 text-sm text-slate-500">
        No profile selected. Open this page from the profile dashboard.
      </div>
    );
  }

  return (
    <ChatPanel
      title={
        profile
          ? `${profile.name}'s Professional Representative`
          : "MyRep"
      }
      subtitle={profile?.headline || undefined}
      backHref={`/profile?id=${profileId}`}
      backLabel="Workspace"
      voiceHref={`/profile/voice?id=${profileId}`}
      activeChatHref={`/profile/chat?id=${encodeURIComponent(profileId)}`}
      askFn={askFn}
      knowledgeReady={knowledgeReady}
      disabled={!!profileError}
      disabledReason={
        profileError
          ? `Profile not loaded: ${profileError}`
          : undefined
      }
      knowledgeWarning={
        <div className="flex items-center justify-between border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-700">
          <span>
            MyRep doesn&apos;t have materials to answer from yet.
          </span>
          <a
            href={`/profile?id=${profileId}`}
            className="ml-3 shrink-0 font-medium underline"
          >
            Profile
          </a>
        </div>
      }
    />
  );
}

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-dvh items-center justify-center text-xs text-gray-400">
          Loading…
        </div>
      }
    >
      <PrivateChatView />
    </Suspense>
  );
}
