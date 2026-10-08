"use client";

import React, { useState, useRef } from "react";
import { DocumentStatusItem, KnowledgeStatus } from "@/types/knowledge";
import { uploadDocument } from "@/lib/api";
import { DocumentItem } from "@/types/document";

interface Props {
  profileId: string;
  knowledgeStatus: KnowledgeStatus | null;
  documents: DocumentStatusItem[];
  loadingDocs: boolean;
  docError: string | null;
  onIndexDocument: (docId: string) => void;
  indexingIds: Set<string>;
  onUploadSuccess: (doc: DocumentItem) => void;
}

export default function ModernKnowledgeBase({
  profileId,
  knowledgeStatus,
  documents,
  loadingDocs,
  docError,
  onIndexDocument,
  indexingIds,
  onUploadSuccess,
}: Props) {
  const [uploading, setUploading] = useState(false);
  const [uploadStep, setUploadStep] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setUploadError("Only PDF documents are supported for knowledge grounding.");
      return;
    }

    setUploading(true);
    setUploadError(null);
    setUploadStep("Extracting & Uploading...");

    try {
      const doc = await uploadDocument(profileId, file);
      setUploadStep("Document Uploaded ✓");
      onUploadSuccess(doc);
      setTimeout(() => {
        setUploadStep(null);
        setUploading(false);
      }, 1500);
    } catch (err: unknown) {
      setUploadError(
        err instanceof Error ? err.message : "Upload failed. Please ensure the backend is running."
      );
      setUploading(false);
      setUploadStep(null);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const onFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <section
      className="rounded-[22px] border border-[#F0E6DE] bg-white px-5 py-5 sm:px-6"
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-3xl text-[#16161D]">Knowledge</h2>
          <p className="mt-2 max-w-md text-sm leading-relaxed text-[#6B6574]">
            Add documents so your Rep can answer with accurate information.
          </p>
          {knowledgeStatus && (
            <p className="mt-2 text-sm text-[#8A8494]">
              {knowledgeStatus.indexed_documents} of {knowledgeStatus.total_documents} ready
              {knowledgeStatus.total_documents > 0 && !knowledgeStatus.rag_ready ? " · getting ready" : ""}
            </p>
          )}
        </div>
        <button
          type="button"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
          className="shrink-0 rounded-full border border-[#E4D4F0] bg-[#F8F1FC] px-3.5 py-2 text-sm text-[#6D4E86] transition hover:bg-[#F3E8FA] disabled:opacity-50"
        >
          {uploading ? uploadStep || "Adding…" : "+ Add document"}
        </button>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,application/pdf"
        onChange={onFileInputChange}
        className="hidden"
      />
      {dragOver && (
        <p className="mt-3 rounded-2xl border border-dashed border-[#D4B8D8] bg-[#FBF8F4] px-4 py-3 text-sm text-[#6B6574]">
          Drop a PDF to add it.
        </p>
      )}

      {uploadError && (
        <p className="mt-3 text-sm text-red-700" role="alert">
          {uploadError}
        </p>
      )}

      <div className="mt-5 divide-y divide-[#F3EBE3]">
        {loadingDocs && <p className="py-6 text-sm text-[#8A8494]">Loading documents…</p>}
        {docError && (
          <p className="py-4 text-sm text-red-700" role="alert">
            {docError}
          </p>
        )}
        {!loadingDocs && documents.length === 0 && (
          <p className="py-6 text-sm text-[#8A8494]">No documents yet. Add a resume or notes.</p>
        )}

        {documents.map((doc) => {
          const isIndexing = indexingIds.has(doc.id) || doc.indexing_status === "INDEXING";
          const isIndexed = doc.indexing_status === "INDEXED";
          const isFailed = doc.indexing_status === "FAILED" && !indexingIds.has(doc.id);
          const status = isFailed ? "Couldn't get ready" : isIndexed ? "Ready" : "Getting ready…";

          return (
            <div key={doc.id} className="flex items-center justify-between gap-3 py-3.5">
              <div className="min-w-0">
                <p className="truncate text-sm text-[#16161D]">{doc.filename}</p>
                <p className="mt-0.5 text-xs text-[#8A8494]">
                  Uploaded {new Date(doc.created_at).toLocaleDateString()}
                  {doc.indexed_chunks != null ? ` · ${doc.indexed_chunks} sections` : ""}
                </p>
                {isFailed && doc.indexing_error && (
                  <p className="mt-1 text-xs text-red-700">{doc.indexing_error}</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className={`text-sm ${isIndexed ? "text-[#0F766E]" : "text-[#8A8494]"}`}>
                  {isIndexed ? "✓ " : ""}
                  {status}
                </span>
                {isFailed && (
                  <button
                    type="button"
                    onClick={() => onIndexDocument(doc.id)}
                    disabled={isIndexing}
                    className="text-sm text-[#5C5666] underline-offset-4 hover:underline disabled:opacity-50"
                  >
                    Try again
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
