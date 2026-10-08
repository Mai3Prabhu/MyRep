"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { PublicProfile } from "@/types/public";
import { getPublicProfile } from "@/lib/api";
import PublicSection from "@/components/public/PublicSection";
import RepAvatar from "@/components/brand/RepAvatar";
import RepNavbar from "@/components/brand/RepNavbar";

function skillLabel(item: unknown): string {
  if (typeof item === "string") return item.trim();
  if (item && typeof item === "object" && "name" in item) {
    const name = (item as { name?: unknown }).name;
    return typeof name === "string" ? name.trim() : "";
  }
  return "";
}

export default function PublicProfilePage() {
  const params = useParams<{ profile_id: string }>();
  const profileId = params.profile_id;

  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    if (!profileId) return;
    setLoading(true);
    getPublicProfile(profileId)
      .then((data) => {
        setProfile(data);
        setUnavailable(false);
      })
      .catch(() => {
        setProfile(null);
        setUnavailable(true);
      })
      .finally(() => setLoading(false));
  }, [profileId]);

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#FBF8F4]">
        <RepAvatar size="md" state="thinking" interactive={false} />
      </div>
    );
  }

  if (unavailable || !profile) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#FBF8F4] px-6 text-center">
        <RepAvatar size="md" state="idle" />
        <h1 className="font-display mt-6 text-3xl">This profile is private.</h1>
        <Link href="/" className="mt-6 text-sm text-[#5C5666] underline-offset-4 hover:underline">
          MyRep
        </Link>
      </div>
    );
  }

  const skills = (profile.skills || []).map(skillLabel).filter(Boolean);
  const question = `What projects has ${profile.name} built?`;

  return (
    <div className="min-h-screen bg-[#FBF8F4] text-[#16161D]">
      <RepNavbar chatHref={`/rep/${profile.id}/chat`} />

      <main className="mx-auto flex w-full max-w-xl flex-col items-center px-6 py-16 text-center">
        <RepAvatar size="lg" state="happy" interactive={false} />
        <h1 className="font-display mt-8 text-5xl">{profile.name}</h1>
        {profile.headline && (
          <p className="mt-3 text-base text-[#5C5666]">{profile.headline}</p>
        )}
        {skills.length > 0 && (
          <p className="mt-5 text-sm tracking-wide text-[#6B6574]">{skills.join("  ·  ")}</p>
        )}

        <Link
          href={`/rep/${profile.id}/chat`}
          className="mt-10 inline-flex rounded-full bg-[#16161D] px-5 py-2.5 text-sm text-white"
        >
          Talk to my Rep
        </Link>
        <p className="mt-6 text-sm text-[#5C5666]">Ask my Rep anything about my work</p>
        <Link
          href={`/rep/${profile.id}/chat`}
          className="mt-3 text-sm text-[#16161D] underline-offset-4 hover:underline"
        >
          {question}
        </Link>
        <Link
          href={`/rep/${profile.id}/voice`}
          aria-label="Voice"
          title="Voice"
          className="mt-8 text-lg text-[#16161D]"
        >
          🎙
        </Link>

        {(profile.about || profile.projects || profile.experience || profile.education) && (
          <div className="mt-16 w-full space-y-10 text-left">
            {profile.about && (
              <p className="text-sm leading-relaxed text-[#3D3A45]">{profile.about}</p>
            )}
            <PublicSection title="Projects" items={profile.projects} />
            <PublicSection title="Experience" items={profile.experience} />
            <PublicSection title="Education" items={profile.education} />
          </div>
        )}
      </main>
    </div>
  );
}
