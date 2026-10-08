"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { Profile } from "@/types/profile";
import { getProfile } from "@/lib/api";

const VoicePanel = dynamic(() => import("@/components/voice/VoicePanel"), {
  ssr: false,
});

function PrivateVoiceView() {
  const searchParams = useSearchParams();
  const profileId = searchParams.get("id") || "";
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!profileId) return;
    getProfile(profileId)
      .then(setProfile)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Profile not found.");
      });
  }, [profileId]);

  if (!profileId) {
    return (
      <div className="flex h-dvh items-center justify-center px-4 text-sm text-slate-500">
        No profile selected. Open this page from the profile dashboard.
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-dvh items-center justify-center px-4 text-sm text-red-700">
        {error}
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="flex h-dvh items-center justify-center text-xs text-slate-400">
        Loading…
      </div>
    );
  }

  return (
    <VoicePanel
      profileId={profile.id}
      profileName={profile.name}
      visibility="private"
      chatHref={`/profile/chat?id=${profile.id}`}
      backHref={`/profile?id=${profile.id}`}
      backLabel="Knowledge Base"
    />
  );
}

export default function PrivateVoicePage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-dvh items-center justify-center text-xs text-gray-400">
          Loading…
        </div>
      }
    >
      <PrivateVoiceView />
    </Suspense>
  );
}
