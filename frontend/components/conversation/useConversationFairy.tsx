"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RepState } from "@/components/brand/RepAvatar";
import { useFairyFlight } from "@/components/conversation/FairyFlight";
import { visibleTarget } from "@/components/conversation/ConversationSummaryView";
import {
  ConversationSummary,
  EMPTY_SUMMARY,
  applyTurnSummary,
  captureQuestion,
} from "@/lib/conversationSummary";
import { TurnSummary } from "@/types/chat";

/**
 * Turn-level fairy choreography shared by text chat and voice.
 *
 *   capture(id, question)   — a submitted (text) or final (voice) turn
 *   organize(id, digest)    — the Rep's answer for that turn arrived
 *
 * Called once per turn, never per token. capture and organize are idempotent
 * and order-independent, so a fast answer that lands mid-flight is safe.
 */

const ORGANIZING_MS = 900;
const EVIDENCE_MS = 1100;

function nextFrame() {
  return new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
}

export function useConversationFairy(baseState: RepState) {
  const [summary, setSummary] = useState<ConversationSummary>(EMPTY_SUMMARY);
  const [overlay, setOverlay] = useState<RepState | null>(null);
  const railRef = useRef<HTMLDivElement>(null);
  const pillRef = useRef<HTMLButtonElement>(null);
  const timers = useRef<number[]>([]);
  const { fly, layer } = useFairyFlight();

  const clearTimers = useCallback(() => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const capture = useCallback(
    async (id: string, question: string, source: () => Element | null) => {
      clearTimers();
      setOverlay("capturing");
      // Let the new message (and the mobile landing pill) render before measuring.
      await nextFrame();
      await fly(source(), visibleTarget(railRef.current, pillRef.current), question);
      setSummary((current) => captureQuestion(current, id, question));
      setOverlay((current) => (current === "capturing" ? null : current));
    },
    [clearTimers, fly]
  );

  const organize = useCallback(
    (id: string, digest: TurnSummary | null | undefined, evidenceShown: boolean) => {
      clearTimers();
      setSummary((current) => applyTurnSummary(current, id, digest));
      setOverlay("organizing");
      timers.current.push(
        window.setTimeout(() => {
          setOverlay(evidenceShown ? "evidence_found" : null);
          if (evidenceShown) {
            timers.current.push(window.setTimeout(() => setOverlay(null), EVIDENCE_MS));
          }
        }, ORGANIZING_MS)
      );
    },
    [clearTimers]
  );

  /** A turn ended without an answer (error, interrupt): settle the fairy. */
  const settle = useCallback(() => {
    clearTimers();
    setOverlay(null);
  }, [clearTimers]);

  return {
    summary,
    /** The fairy's state for the summary area. */
    repState: overlay ?? baseState,
    /** Only the capture moment, for avatars that otherwise follow live status. */
    capturing: overlay === "capturing",
    railRef,
    pillRef,
    flightLayer: layer,
    capture,
    organize,
    settle,
  };
}
