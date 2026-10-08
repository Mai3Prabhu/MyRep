"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { PublicProfile } from "@/types/public";
import { getPublicProfile } from "@/lib/api";

const VoicePanel = dynamic(() => import("@/components/voice/VoicePanel"), {
  ssr: false,
});

export default function PublicVoicePage() {
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
          Public voice is only available for shared profiles.
        </p>
      </div>
    );
  }

  return (
    <VoicePanel
      profileId={profile.id}
      profileName={profile.name}
      visibility="public"
      chatHref={`/rep/${profile.id}/chat`}
      backHref={`/rep/${profile.id}`}
      backLabel="Profile"
    />
  );
}
