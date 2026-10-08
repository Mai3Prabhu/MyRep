"use client";

import { useState } from "react";
import { SourceDisplay } from "@/types/chat";

interface Props {
  sources: SourceDisplay[];
}

const VISIBLE = 3;

/**
 * Sources the Rep consulted for a grounded answer.
 *
 * Shows exactly what the backend returned: filename · page, plus a verbatim
 * excerpt on private routes. Public routes never receive excerpts. Rendered
 * only for answered turns (see shouldShowEvidence) — never for "I don't have
 * enough information" replies.
 */
export default function SourceReferences({ sources }: Props) {
  const [expanded, setExpanded] = useState(false);

  // One row per document page; keep the first (highest-ranked) excerpt.
  const unique: SourceDisplay[] = [];
  const seen = new Set<string>();
  for (const src of sources) {
    const key = `${src.filename}#${src.page_number}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(src);
  }
  if (unique.length === 0) return null;

  const shown = expanded ? unique : unique.slice(0, VISIBLE);
  const hidden = unique.length - shown.length;

  return (
    <div className="rep-fade-up mt-3.5 border-t border-slate-100 pt-3" aria-label="Sources consulted">
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
        <span className="text-[#C9A93B]" aria-hidden="true">
          ✦
        </span>
        Sources consulted
      </p>

      <ul className="mt-2 space-y-2">
        {shown.map((src) => (
          <li key={`${src.filename}#${src.page_number}`} className="text-[11px] leading-snug">
            <p className="text-slate-700">
              <span className="font-semibold text-slate-800">{src.filename}</span>
              <span className="text-slate-400"> · p. {src.page_number}</span>
            </p>
            {src.excerpt && (
              <p className="mt-0.5 line-clamp-2 border-l-2 border-[#E9D5FF] pl-2 italic text-slate-500">
                “{src.excerpt}”
              </p>
            )}
          </li>
        ))}
      </ul>

      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-2 text-[11px] font-medium text-slate-500 underline-offset-2 hover:underline"
        >
          +{hidden} more
        </button>
      )}
    </div>
  );
}
