"use client";

import { DocumentStatusItem } from "@/types/knowledge";
import DocumentStatusCard from "./DocumentStatusCard";

interface Props {
  documents: DocumentStatusItem[];
  loading: boolean;
  error: string | null;
  onIndex: (documentId: string) => void;
  indexingIds: Set<string>;
}

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-lg border border-gray-200 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="h-4 w-48 rounded bg-gray-200" />
        <div className="h-5 w-20 rounded-full bg-gray-200" />
      </div>
      <div className="mt-2 h-3 w-32 rounded bg-gray-100" />
    </div>
  );
}

export default function DocumentStatusList({
  documents,
  loading,
  error,
  onIndex,
  indexingIds,
}: Props) {
  if (loading) {
    return (
      <div className="space-y-3" aria-label="Loading documents">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Could not load documents: {error}
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
        <p className="text-sm text-gray-500">
          No documents yet. Upload a PDF above to build your knowledge base.
        </p>
      </div>
    );
  }

  return (
    <ul className="space-y-3" aria-label="Documents">
      {documents.map((doc) => (
        <li key={doc.id}>
          <DocumentStatusCard
            doc={doc}
            onIndex={onIndex}
            isIndexing={indexingIds.has(doc.id)}
          />
        </li>
      ))}
    </ul>
  );
}
