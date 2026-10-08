"use client";

import React from "react";

/**
 * Fairy states. Conversation states are driven by completed turn events,
 * never by streaming tokens:
 *   listening → capturing (question picked up) → thinking → organizing
 *   (summary updated) → evidence_found (if sources) → speaking → idle
 */
export type RepState =
  | "idle"
  | "listening"
  | "thinking"
  | "capturing"
  | "organizing"
  | "evidence_found"
  | "speaking"
  | "happy";
export type RepSize = "xs" | "sm" | "md" | "lg" | "xl" | "hero";

interface RepAvatarProps {
  state?: RepState;
  size?: RepSize;
  className?: string;
  showBadge?: boolean;
  interactive?: boolean;
  /** No ambient float/glow — for avatars repeated in message history. */
  still?: boolean;
}

const SIZE_MAP: Record<RepSize, { container: string; pxSize: number }> = {
  xs: { container: "w-7 h-7", pxSize: 28 },
  sm: { container: "w-10 h-10", pxSize: 40 },
  md: { container: "w-16 h-16", pxSize: 64 },
  lg: { container: "w-24 h-24", pxSize: 96 },
  xl: { container: "w-32 h-32", pxSize: 128 },
  hero: { container: "w-44 h-44 sm:w-60 sm:h-60", pxSize: 240 },
};

const STATE_LABEL: Record<RepState, string> = {
  idle: "ready",
  listening: "listening",
  thinking: "thinking",
  capturing: "noting your question",
  organizing: "organizing the conversation",
  evidence_found: "found supporting sources",
  speaking: "speaking",
  happy: "ready",
};

function auraClass(state: RepState): string {
  switch (state) {
    case "listening":
      return "scale-135 opacity-90 animate-pulse bg-purple-500/40";
    case "speaking":
      return "scale-125 opacity-80 animate-rep-glow";
    case "thinking":
      return "scale-120 opacity-70 animate-spin [animation-duration:9s]";
    case "capturing":
      return "scale-125 opacity-90 bg-[#F0D56A]/45";
    case "organizing":
      return "scale-125 opacity-80 bg-[#E7D4F5]/70";
    case "evidence_found":
      return "scale-120 opacity-80 bg-teal-300/40";
    default:
      return "scale-110 opacity-60 animate-rep-glow";
  }
}

export default function RepAvatar({
  state = "idle",
  size = "md",
  className = "",
  showBadge = false,
  interactive = true,
  still = false,
}: RepAvatarProps) {
  const { container } = SIZE_MAP[size];

  const isListening = state === "listening";
  const isThinking = state === "thinking";
  const isSpeaking = state === "speaking";

  return (
    <div
      className={`relative inline-flex items-center justify-center select-none ${container} ${className}`}
      role="img"
      aria-label={`Rep, ${STATE_LABEL[state]}`}
    >
      {/* Soft aura */}
      <div
        className={`absolute inset-0 rounded-full bg-[#E7D4F5]/40 blur-2xl transition-all duration-700 pointer-events-none ${
          still ? "scale-105 opacity-40" : auraClass(state)
        }`}
      />

      {isListening && !still && (
        <>
          <span className="absolute inset-0 rounded-full border-2 border-purple-400/50 animate-ping [animation-duration:2s] pointer-events-none" />
          <span className="absolute -inset-3 rounded-full border border-yellow-300/40 animate-pulse pointer-events-none" />
        </>
      )}

      {/* Organizing: two sparkles circle the fairy while the summary updates */}
      {state === "organizing" && !still && (
        <span className="rep-orbit pointer-events-none absolute -inset-2" aria-hidden="true">
          <span className="absolute left-1/2 top-0 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-[#F0D56A]" />
          <span className="absolute bottom-0 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-purple-300" />
        </span>
      )}

      {/* Evidence found: one soft teal ring */}
      {state === "evidence_found" && !still && (
        <span className="rep-evidence-ring pointer-events-none absolute -inset-1 rounded-full border-2 border-teal-400/70" />
      )}

      <div
        className={`relative w-full h-full rounded-full overflow-hidden flex items-center justify-center transition-transform duration-300 ${
          !still && state !== "speaking" ? "animate-rep-float" : ""
        } ${state === "capturing" && !still ? "rep-capture" : ""} ${
          interactive ? "hover:scale-105 active:scale-95 cursor-pointer" : ""
        }`}
      >
        <img
          src="/images/rep-chosen.png?v=2"
          alt=""
          className="h-full w-full rounded-full object-cover object-top"
        />

        {isSpeaking && !still && (
          <div className="absolute inset-x-0 bottom-1 flex items-end justify-center gap-0.5 h-6 bg-gradient-to-t from-purple-900/60 to-transparent pb-1">
            <span className="w-1 bg-yellow-300 rounded-full rep-wave-on" />
            <span className="w-1 bg-purple-200 rounded-full rep-wave-on" />
            <span className="w-1 bg-yellow-300 rounded-full rep-wave-on" />
            <span className="w-1 bg-purple-200 rounded-full rep-wave-on" />
          </div>
        )}
      </div>

      {showBadge && (
        <span
          className={`absolute -bottom-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full border-2 border-white ${
            isListening
              ? "bg-purple-600 animate-pulse"
              : isSpeaking
              ? "bg-purple-700 animate-bounce"
              : isThinking
              ? "bg-amber-400"
              : "bg-emerald-500"
          }`}
          title={`Status: ${state}`}
        />
      )}
    </div>
  );
}
