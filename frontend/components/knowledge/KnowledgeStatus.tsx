"use client";

import { KnowledgeStatus as KnowledgeStatusType } from "@/types/knowledge";

interface Props {
  status: KnowledgeStatusType | null;
  loading: boolean;
  error: string | null;
}

function StatusBadge({
  rag_ready,
  indexed,
  total,
  failed,
}: {
  rag_ready: boolean;
  indexed: number;
  total: number;
  failed: number;
}) {
  if (total === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-500">
        No documents uploaded yet. Upload a PDF below to build your knowledge base.
      </div>
    );
  }

  if (rag_ready && indexed === total && failed === 0) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-green-200 bg-green-50 p-4">
        <span className="mt-0.5 text-green-600" aria-hidden="true">
          ✓
        </span>
        <div>
          <p className="text-sm font-medium text-green-800">
            Knowledge base ready
          </p>
          <p className="text-sm text-green-700">
            All {total} document{total !== 1 ? "s" : ""} indexed and searchable.
          </p>
        </div>
      </div>
    );
  }

  if (rag_ready) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
        <span className="mt-0.5 text-blue-600" aria-hidden="true">
          ℹ
        </span>
        <div>
          <p className="text-sm font-medium text-blue-800">
            Partially ready — {indexed} of {total} document
            {total !== 1 ? "s" : ""} indexed
          </p>
          {failed > 0 && (
            <p className="text-sm text-blue-700">
              {failed} document{failed !== 1 ? "s" : ""} failed indexing —
              retry below.
            </p>
          )}
        </div>
      </div>
    );
  }

  if (failed > 0 && failed === total) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
        <span className="mt-0.5 text-red-600" aria-hidden="true">
          ✕
        </span>
        <div>
          <p className="text-sm font-medium text-red-800">
            Indexing failed for all documents
          </p>
          <p className="text-sm text-red-700">
            Retry indexing below to make this knowledge base searchable.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
      <span className="mt-0.5 text-amber-600" aria-hidden="true">
        ⚠
      </span>
      <div>
        <p className="text-sm font-medium text-amber-800">
          Not ready — {total - indexed} document{total - indexed !== 1 ? "s" : ""}{" "}
          not yet indexed
        </p>
        <p className="text-sm text-amber-700">
          Index your documents below so they can be searched.
          {failed > 0 && ` ${failed} document${failed !== 1 ? "s" : ""} need retrying.`}
        </p>
      </div>
    </div>
  );
}

export default function KnowledgeStatus({ status, loading, error }: Props) {
  if (loading) {
    return (
      <div
        className="h-16 animate-pulse rounded-lg bg-gray-100"
        aria-label="Loading knowledge status"
      />
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Could not load knowledge status: {error}
      </div>
    );
  }

  if (!status) return null;

  return (
    <StatusBadge
      rag_ready={status.rag_ready}
      indexed={status.indexed_documents}
      total={status.total_documents}
      failed={status.failed_documents}
    />
  );
}
