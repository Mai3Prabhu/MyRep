"use client";

import { useEffect, useState, useCallback, useRef, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Profile } from "@/types/profile";
import { DocumentItem } from "@/types/document";
import { DocumentStatusItem, KnowledgeStatus as KnowledgeStatusType } from "@/types/knowledge";
import {
  getProfile,
  getKnowledgeStatus,
  getDocumentStatuses,
  indexDocument,
} from "@/lib/api";
import RepNavbar from "@/components/brand/RepNavbar";
import RepAvatar from "@/components/brand/RepAvatar";
import StructuredProfileEditor from "@/components/profile/StructuredProfileEditor";
import { saveProfileId } from "@/lib/profileSession";
import ModernKnowledgeBase from "@/components/knowledge/ModernKnowledgeBase";
import PublicVisibilityToggle from "@/components/profile/PublicVisibilityToggle";

function ProfileWorkspaceView() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const idFromUrl = searchParams.get("id") || "";
  const [profileIdInput, setProfileIdInput] = useState(idFromUrl);
  const [activeProfileId, setActiveProfileId] = useState(idFromUrl);

  // Profile data
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Knowledge base
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatusType | null>(null);
  const [documentStatuses, setDocumentStatuses] = useState<DocumentStatusItem[]>([]);
  const [loadingDocStatuses, setLoadingDocStatuses] = useState(false);
  const [docStatusError, setDocStatusError] = useState<string | null>(null);
  const [indexingIds, setIndexingIds] = useState<Set<string>>(new Set());
  const autoIndexStarted = useRef<Set<string>>(new Set());

  // Copy UUID notification
  const [copiedId, setCopiedId] = useState(false);

  // Fetchers
  const fetchProfile = useCallback(async (id: string) => {
    if (!id.trim()) return;
    setLoadingProfile(true);
    setProfileError(null);
    try {
      const data = await getProfile(id.trim());
      setProfile(data);
      saveProfileId(data.id);
    } catch (err: unknown) {
      setProfile(null);
      setProfileError(
        err instanceof Error ? err.message : "Failed to load profile details."
      );
    } finally {
      setLoadingProfile(false);
    }
  }, []);

  const fetchKnowledgeData = useCallback(async (id: string) => {
    if (!id.trim()) return;
    setLoadingDocStatuses(true);
    setDocStatusError(null);

    const [statusResult, docsResult] = await Promise.allSettled([
      getKnowledgeStatus(id.trim()),
      getDocumentStatuses(id.trim()),
    ]);

    if (statusResult.status === "fulfilled") {
      setKnowledgeStatus(statusResult.value);
    } else {
      setKnowledgeStatus(null);
    }

    if (docsResult.status === "fulfilled") {
      setDocumentStatuses(docsResult.value);
    } else {
      const err = docsResult.reason;
      setDocStatusError(
        err instanceof Error ? err.message : "Failed to load document list."
      );
    }
    setLoadingDocStatuses(false);
  }, []);

  useEffect(() => {
    if (activeProfileId) {
      fetchProfile(activeProfileId);
      fetchKnowledgeData(activeProfileId);
    }
  }, [activeProfileId, fetchProfile, fetchKnowledgeData]);

  const handleLookup = (e: React.FormEvent) => {
    e.preventDefault();
    if (!profileIdInput.trim()) return;
    setActiveProfileId(profileIdInput.trim());
    router.push(`/profile?id=${encodeURIComponent(profileIdInput.trim())}`);
  };

  const handleProfileUpdated = (updated: Profile) => {
    setProfile(updated);
  };

  const handleUploadSuccess = (doc: DocumentItem) => {
    autoIndexStarted.current.add(doc.id);
    if (activeProfileId) {
      void fetchKnowledgeData(activeProfileId);
    }
    void handleIndexDocument(doc.id);
  };

  const handleIndexDocument = useCallback(
    async (documentId: string) => {
      setIndexingIds((prev) => new Set(prev).add(documentId));
      try {
        await indexDocument(documentId);
      } catch {
        // Will reflect in statuses
      } finally {
        setIndexingIds((prev) => {
          const next = new Set(prev);
          next.delete(documentId);
          return next;
        });
        if (activeProfileId) {
          await fetchKnowledgeData(activeProfileId);
        }
      }
    },
    [activeProfileId, fetchKnowledgeData]
  );

  useEffect(() => {
    for (const doc of documentStatuses) {
      const needsIndex =
        doc.indexing_status === "NOT_INDEXED" || doc.indexing_status === "INDEXING";
      if (!needsIndex || autoIndexStarted.current.has(doc.id)) {
        continue;
      }
      autoIndexStarted.current.add(doc.id);
      void handleIndexDocument(doc.id);
    }
  }, [documentStatuses, handleIndexDocument]);

  const copyProfileId = () => {
    if (profile?.id) {
      navigator.clipboard.writeText(profile.id);
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2000);
    }
  };

  return (
    <div className="min-h-screen bg-[#FBF8F4] text-[#16161D]">
      <RepNavbar
        chatHref={profile ? `/profile/chat?id=${encodeURIComponent(profile.id)}` : undefined}
        profileHref={profile ? `/profile?id=${encodeURIComponent(profile.id)}` : undefined}
      />

      <main className="mx-auto w-full max-w-[1180px] space-y-8 px-6 py-10 md:px-10">

        {/* Loading state */}
        {loadingProfile && (
          <div className="rounded-3xl border border-slate-200 bg-white p-12 text-center text-sm text-slate-500">
            <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-teal-600 border-t-transparent" />
            Loading your MyRep workspace...
          </div>
        )}

        {/* Error state */}
        {profileError && (
          <div className="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-800">
            <h4 className="font-bold">Could not load profile</h4>
            <p className="mt-1 text-xs">{profileError}</p>
            <p className="mt-3 text-xs text-red-600">
              Ensure your backend server is running and the id matches an existing profile. You can
              create a new profile from the <Link href="/create" className="underline">create page</Link>.
            </p>
          </div>
        )}

        {/* Empty state: No profile ID */}
        {!loadingProfile && !profile && !profileError && (
          <div className="py-16 text-center">
            <div className="flex justify-center">
              <RepAvatar size="md" state="idle" />
            </div>
            <h2 className="font-display mt-6 text-3xl">Your workspace</h2>
            <form onSubmit={handleLookup} className="mx-auto mt-8 max-w-sm space-y-3 text-left">
              <label className="block text-sm text-[#3D3A45]" htmlFor="profile-id">
                Profile id
              </label>
              <input
                id="profile-id"
                type="text"
                value={profileIdInput}
                onChange={(e) => setProfileIdInput(e.target.value)}
                className="w-full rounded-2xl border border-[#E6DFD4] bg-white px-4 py-2.5 text-sm outline-none focus:border-[#C8B6D8]"
              />
              <button
                type="submit"
                className="rounded-full bg-[#16161D] px-5 py-2.5 text-sm text-white"
              >
                Continue →
              </button>
            </form>
            <Link href="/create" className="mt-6 inline-block text-sm text-[#5C5666] underline-offset-4 hover:underline">
              Create MyRep
            </Link>
          </div>
        )}

        {!loadingProfile && profile && (
          <div className="space-y-8">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h1 className="font-display text-4xl leading-none text-[#16161D] sm:text-5xl">
                  Build your <span className="text-[#9B4D86]">Rep</span>
                </h1>
                <p className="mt-3 max-w-md text-sm leading-relaxed text-[#5C5666] sm:text-base">
                  Share your experience, work and knowledge. I&apos;ll use this to represent you accurately.
                </p>
                <button
                  type="button"
                  onClick={copyProfileId}
                  className="mt-2 text-xs text-[#A39EAA] hover:text-[#5C5666]"
                  title="Copy profile id"
                >
                  {copiedId ? "Id copied" : "Copy id"}
                </button>
              </div>
              <div className="flex items-center gap-4">
                <Link
                  href={`/profile/voice?id=${encodeURIComponent(profile.id)}`}
                  className="text-sm text-[#6B6574] underline-offset-4 hover:text-[#16161D] hover:underline"
                >
                  Voice
                </Link>
                <Link
                  href={`/profile/chat?id=${encodeURIComponent(profile.id)}`}
                  className="inline-flex h-11 items-center justify-center rounded-full bg-[#16161D] px-5 text-sm text-white transition hover:bg-[#2C2C34]"
                >
                  Preview MyRep →
                </Link>
              </div>
            </div>

            <StructuredProfileEditor
              profile={profile}
              onProfileUpdated={handleProfileUpdated}
              documentCount={documentStatuses.length}
              indexedCount={knowledgeStatus?.indexed_documents ?? 0}
              knowledge={
                <ModernKnowledgeBase
                  profileId={profile.id}
                  knowledgeStatus={knowledgeStatus}
                  documents={documentStatuses}
                  loadingDocs={loadingDocStatuses}
                  docError={docStatusError}
                  onIndexDocument={handleIndexDocument}
                  indexingIds={indexingIds}
                  onUploadSuccess={handleUploadSuccess}
                />
              }
              visibility={
                <PublicVisibilityToggle profile={profile} onUpdated={handleProfileUpdated} />
              }
            />
          </div>
        )}
      </main>
    </div>
  );
}

export default function ProfilePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-xs text-slate-500">
          Loading MyRep Workspace...
        </div>
      }
    >
      <ProfileWorkspaceView />
    </Suspense>
  );
}
