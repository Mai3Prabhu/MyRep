"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ConversationTurn } from "@/types/chat";
import { PublicProfile } from "@/types/public";
import { askPublicMyRep, getPublicProfile } from "@/lib/api";
import ChatPanel from "@/components/chat/ChatPanel";

export default function PublicChatPage() {
  const params = useParams<{ profile_id: string }>();
  const profileId = params.profile_id;

  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!profileId) return;
    getPublicProfile(profileId)
      .then(setProfile)
      .catch(() => setUnavailable(true))
      .finally(() => setLoading(false));
  }, [profileId]);

  const askFn = useCallback(
    async (question: string, history: ConversationTurn[]) => {
      const response = await askPublicMyRep(profileId, question, history);
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

  if (loading) {
    return (
      <div className="flex h-dvh items-center justify-center text-xs text-slate-400">
        Loading…
      </div>
    );
  }

  if (unavailable || !profile) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center px-4 text-center">
        <p className="text-lg font-semibold text-slate-800">
          This profile is not available.
        </p>
        <p className="mt-2 text-sm text-slate-500">
          Public conversation is only available for shared profiles.
        </p>
      </div>
    );
  }

  return (
    <ChatPanel
      title={`Talk to ${profile.name}`}
      subtitle={profile.headline || "AI Professional Representative"}
      backHref={`/rep/${profile.id}`}
      backLabel="Profile"
      voiceHref={`/rep/${profile.id}/voice`}
      activeChatHref={`/rep/${profile.id}/chat`}
      askFn={askFn}
      knowledgeReady={profile.knowledge_ready}
      blockWhenNotReady
      knowledgeWarning={
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-700">
          MyRep doesn&apos;t have enough material to answer that yet.
        </div>
      }
    />
  );
}
