import type { Metadata } from "next";
import { PublicProfile } from "@/types/public";

export const dynamic = "force-dynamic";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

async function fetchPublicProfile(
  profileId: string
): Promise<PublicProfile | null> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/v1/public/profiles/${profileId}`,
      { headers: { Accept: "application/json" }, cache: "no-store" }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ profile_id: string }>;
}): Promise<Metadata> {
  const { profile_id } = await params;
  const profile = await fetchPublicProfile(profile_id);

  if (!profile) {
    return {
      title: "MyRep",
      robots: { index: false, follow: false },
    };
  }

  const title = profile.headline
    ? `${profile.name} — ${profile.headline} | MyRep`
    : `${profile.name} | MyRep`;

  const description =
    (profile.about && profile.about.trim().slice(0, 160)) ||
    `Talk to ${profile.name}'s AI professional representative.`;

  return { title, description };
}

export default function PublicRepLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
