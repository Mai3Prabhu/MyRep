"use client";

import { useState, useRef } from "react";
import { uploadDocument } from "@/lib/api";
import { DocumentItem } from "@/types/document";

interface DocumentUploadProps {
  profileId: string;
  onUploadSuccess: (newDoc: DocumentItem) => void;
}

export function DocumentUpload({
  profileId,
  onUploadSuccess,
}: DocumentUploadProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    setSuccessMessage(null);
    const file = e.target.files?.[0];
    if (!file) {
      setSelectedFile(null);
      return;
    }

    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setSelectedFile(file);
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setError("Please select a PDF file to upload.");
      return;
    }

    setUploading(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const doc = await uploadDocument(profileId, selectedFile);
      setSuccessMessage(`Uploaded "${doc.filename}" successfully.`);
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      onUploadSuccess(doc);
    } catch (err: any) {
      setError(err.message || "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-md font-semibold text-slate-800">
        Upload Knowledge Document
      </h3>
      <p className="mt-1 text-xs text-slate-500">
        Attach a PDF (resume, project report, case study) to this profile. Max 10MB.
      </p>

      {error && (
        <div className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {successMessage && (
        <div className="mt-3 rounded border border-green-200 bg-green-50 p-2 text-xs text-green-700">
          {successMessage}
        </div>
      )}

      <form onSubmit={handleUpload} className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileChange}
          disabled={uploading}
          className="block w-full text-xs text-slate-500 file:mr-4 file:rounded file:border-0 file:bg-blue-50 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-blue-700 hover:file:bg-blue-100"
        />

        <button
          type="submit"
          disabled={uploading || !selectedFile}
          className="shrink-0 rounded bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {uploading ? "Uploading..." : "Upload PDF"}
        </button>
      </form>
    </div>
  );
}
