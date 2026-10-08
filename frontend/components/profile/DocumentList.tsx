"use client";

import { DocumentItem } from "@/types/document";

interface DocumentListProps {
  documents: DocumentItem[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function DocumentList({
  documents,
  loading,
  error,
  onRefresh,
}: DocumentListProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div>
          <h3 className="text-md font-semibold text-slate-800">
            Uploaded Documents ({documents.length})
          </h3>
          <p className="text-xs text-slate-500">
            Authoritative documents registered for RAG retrieval in future layers.
          </p>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {loading && documents.length === 0 ? (
        <div className="py-8 text-center text-xs text-slate-500">
          Loading documents...
        </div>
      ) : documents.length === 0 ? (
        <div className="py-8 text-center text-xs text-slate-500">
          No documents uploaded yet for this profile.
        </div>
      ) : (
        <div className="mt-3 divide-y divide-slate-100 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-slate-400">
                <th className="py-2 pr-4 font-medium">Filename</th>
                <th className="py-2 pr-4 font-medium">Size</th>
                <th className="py-2 pr-4 font-medium">Type</th>
                <th className="py-2 pr-4 font-medium">Uploaded At</th>
                <th className="py-2 font-medium">Document ID</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50">
                  <td className="py-2.5 pr-4 font-medium text-slate-900">
                    {doc.filename}
                  </td>
                  <td className="py-2.5 pr-4 text-slate-500">
                    {formatBytes(doc.file_size)}
                  </td>
                  <td className="py-2.5 pr-4 text-slate-500">
                    {doc.content_type}
                  </td>
                  <td className="py-2.5 pr-4 text-slate-500">
                    {new Date(doc.created_at).toLocaleString()}
                  </td>
                  <td className="py-2.5 font-mono text-[10px] text-slate-400">
                    {doc.id}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
