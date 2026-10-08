"use client";

import { useState } from "react";
import Link from "next/link";
import { Profile } from "@/types/profile";
import { updateProfile } from "@/lib/api";

interface Props {
  profile: Profile;
  onUpdated: (updated: Profile) => void;
}

export default function PublicVisibilityToggle({ profile, onUpdated }: Props) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const isPublic = Boolean(profile.is_public);
  const publicPath = `/rep/${profile.id}`;

  const handleToggle = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateProfile(profile.id, { is_public: !isPublic });
      onUpdated(updated);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not update visibility."
      );
    } finally {
      setSaving(false);
    }
  };

  const copyPublicLink = () => {
    const fullUrl = `${window.location.origin}${publicPath}`;
    navigator.clipboard.writeText(fullUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section className="rounded-[22px] border border-[#F0E6DE] bg-white px-5 py-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl text-[#16161D]">Your Rep</h2>
          <p className="mt-2 text-sm font-medium text-[#16161D]">{isPublic ? "Public" : "Private"}</p>
          <p className="mt-1 text-sm leading-relaxed text-[#6B6574]">
            {isPublic
              ? "People with your Rep link can talk to it."
              : "Only you can access your Rep."}
          </p>
        </div>
        <button
          type="button"
          onClick={handleToggle}
          disabled={saving}
          className="shrink-0 rounded-full border border-[#E6DFD4] bg-[#FBF8F3] px-4 py-2 text-sm text-[#16161D] transition hover:bg-[#F7F1E8] disabled:opacity-50"
        >
          {saving ? "Saving…" : isPublic ? "Unpublish" : "Publish Rep"}
        </button>
      </div>
      {error && (
        <p className="mt-3 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
      {isPublic && (
        <div className="mt-4 flex items-center gap-4 text-sm">
          <button type="button" onClick={copyPublicLink} className="text-[#5C5666] underline-offset-4 hover:underline">
            {copied ? "Copied" : "Copy link"}
          </button>
          <Link href={publicPath} className="text-[#16161D] underline-offset-4 hover:underline">
            Open public page
          </Link>
        </div>
      )}
    </section>
  );
}
