"use client";

import { DocumentStatusItem, IndexingStatus } from "@/types/knowledge";

interface Props {
  doc: DocumentStatusItem;
  onIndex: (id: string) => void;
  isIndexing: boolean;
}

const STATUS_LABELS: Record<IndexingStatus, string> = {
  NOT_INDEXED: "Not indexed",
  INDEXING: "Indexing…",
  INDEXED: "Indexed",
  FAILED: "Failed",
};

const STATUS_STYLES: Record<
  IndexingStatus,
  { badge: string; row: string }
> = {
  NOT_INDEXED: {
    badge: "bg-gray-100 text-gray-600",
    row: "",
  },
  INDEXING: {
    badge: "bg-blue-100 text-blue-700 animate-pulse",
    row: "bg-blue-50/30",
  },
  INDEXED: {
    badge: "bg-green-100 text-green-700",
    row: "",
  },
  FAILED: {
    badge: "bg-red-100 text-red-700",
    row: "bg-red-50/30",
  },
};

function formatBytes(bytes: number): string {
  // Not used in this card but kept for future use.
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function DocumentStatusCard({
  doc,
  onIndex,
  isIndexing,
}: Props) {
  const status = doc.indexing_status as IndexingStatus;
  const styles = STATUS_STYLES[status] ?? STATUS_STYLES.NOT_INDEXED;
  const canIndex = status === "NOT_INDEXED" || status === "FAILED";
  const actionLabel = status === "FAILED" ? "Retry indexing" : "Index document";

  return (
    <div
      className={`flex flex-col gap-2 rounded-lg border border-gray-200 p-4 transition-colors ${styles.row}`}
    >
      {/* Top row: filename + badge */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p
          className="max-w-xs break-words text-sm font-medium text-gray-900 sm:max-w-sm"
          title={doc.filename}
        >
          {doc.filename}
        </p>
        <span
          className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${styles.badge}`}
          aria-label={`Indexing status: ${STATUS_LABELS[status]}`}
        >
          {status === "INDEXING" && (
            <span className="mr-1 inline-block h-2 w-2 rounded-full bg-blue-500 align-middle" />
          )}
          {STATUS_LABELS[status]}
        </span>
      </div>

      {/* Meta row: indexed chunks / uploaded date */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
        {doc.indexed_at && (
          <span>Indexed {formatDateTime(doc.indexed_at)}</span>
        )}
        {doc.indexed_chunks != null && (
          <span>{doc.indexed_chunks} chunk{doc.indexed_chunks !== 1 ? "s" : ""}</span>
        )}
        <span>Uploaded {formatDateTime(doc.created_at)}</span>
      </div>

      {/* Error message */}
      {status === "FAILED" && doc.indexing_error && (
        <p className="text-xs text-red-600" role="alert">
          {doc.indexing_error}
        </p>
      )}

      {/* Action */}
      {canIndex && (
        <div>
          <button
            type="button"
            onClick={() => onIndex(doc.id)}
            disabled={isIndexing}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label={`${actionLabel}: ${doc.filename}`}
          >
            {isIndexing ? (
              <span className="flex items-center gap-1.5">
                <svg
                  className="h-3 w-3 animate-spin"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Indexing…
              </span>
            ) : (
              actionLabel
            )}
          </button>
        </div>
      )}
    </div>
  );
}
