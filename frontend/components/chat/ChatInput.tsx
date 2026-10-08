"use client";

import { useRef, useEffect } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  loading: boolean;
  disabled?: boolean;
}

export default function ChatInput({
  value,
  onChange,
  onSend,
  loading,
  disabled,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const isBlocked = loading || disabled;
  const isEmpty = !value.trim();

  return (
    <div className="flex items-end gap-2 rounded-2xl border border-slate-300/80 bg-white p-2.5 shadow-sm focus-within:border-teal-500 focus-within:ring-2 focus-within:ring-teal-100 transition-all">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isBlocked}
        placeholder={loading ? "Rep is checking knowledge documents…" : "Ask Rep about experience, skills, or projects…"}
        rows={1}
        aria-label="Your question for MyRep"
        className="flex-1 resize-none bg-transparent px-2 py-1 text-xs sm:text-sm text-slate-800 placeholder-slate-400 outline-none disabled:opacity-60 max-h-36"
        style={{ minHeight: "1.5rem" }}
      />

      <button
        type="button"
        onClick={onSend}
        disabled={isBlocked || isEmpty}
        aria-label="Send message to MyRep"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-r from-rep-teal-700 to-rep-teal-900 text-white transition-all hover:scale-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {loading ? (
          <svg
            className="h-4 w-4 animate-spin text-teal-200"
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
        ) : (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4"
            aria-hidden="true"
          >
            <path d="M3.105 2.289a.75.75 0 00-.826.95l1.903 6.115a.75.75 0 00.713.525H10.5a.75.75 0 010 1.5H4.895a.75.75 0 00-.713.525l-1.903 6.115a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
          </svg>
        )}
      </button>
    </div>
  );
}
