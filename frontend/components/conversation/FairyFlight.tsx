"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "@/lib/useReducedMotion";

/**
 * The fairy carries a captured question to "What we've discussed".
 *
 * Purely decorative: aria-hidden, pointer-events none, never blocks input,
 * scrolling, the microphone, or playback. Reduced-motion visitors skip the
 * flight entirely and the item simply appears in the summary.
 */

interface Flight {
  id: number;
  label: string;
  from: DOMRect;
  to: DOMRect;
}

const DURATION_MS = 820;
const COURIER = 28;

function FlightItem({ flight, onDone }: { flight: Flight; onDone: (id: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) {
      onDone(flight.id);
      return;
    }
    const fromX = flight.from.left + flight.from.width / 2;
    const fromY = flight.from.top + Math.min(flight.from.height / 2, 24);
    const toX = flight.to.left + flight.to.width / 2;
    const toY = flight.to.top + flight.to.height / 2;
    const dx = toX - fromX;
    const dy = toY - fromY;
    const lift = Math.min(60, Math.abs(dx) * 0.25 + 24);
    const animation = el.animate(
      [
        { transform: "translate(0px, 0px) scale(0.85)", opacity: 0 },
        { offset: 0.14, transform: "translate(0px, -8px) scale(1)", opacity: 1 },
        {
          offset: 0.62,
          transform: `translate(${dx * 0.62}px, ${dy * 0.62 - lift}px) scale(1)`,
          opacity: 1,
        },
        { transform: `translate(${dx}px, ${dy}px) scale(0.55)`, opacity: 0 },
      ],
      { duration: DURATION_MS, easing: "cubic-bezier(0.22, 0.8, 0.3, 1)", fill: "forwards" }
    );
    animation.onfinish = () => onDone(flight.id);
    return () => {
      // Detach first: a StrictMode re-run must not end the flight early.
      animation.onfinish = null;
      animation.cancel();
    };
  }, [flight, onDone]);

  const left = flight.from.left + flight.from.width / 2 - COURIER / 2;
  const top = flight.from.top + Math.min(flight.from.height / 2, 24) - COURIER / 2;

  return (
    <div
      ref={ref}
      className="pointer-events-none fixed z-50 flex items-center gap-1.5"
      style={{ left, top, opacity: 0 }}
    >
      <span className="relative block h-7 w-7 shrink-0">
        <span className="absolute -inset-1.5 rounded-full bg-[#F0D56A]/40 blur-md" />
        <img
          src="/images/rep-chosen.png?v=2"
          alt=""
          className="relative h-7 w-7 rounded-full object-cover object-top shadow-sm"
        />
      </span>
      <span className="max-w-[11rem] truncate rounded-full border border-[#E9D5FF] bg-white/95 px-2.5 py-1 text-[11px] font-medium text-[#3D3A45] shadow-sm">
        {flight.label}
      </span>
    </div>
  );
}

export function useFairyFlight() {
  const [flights, setFlights] = useState<Flight[]>([]);
  const resolvers = useRef(new Map<number, () => void>());
  const seq = useRef(0);

  const done = useCallback((id: number) => {
    resolvers.current.get(id)?.();
    resolvers.current.delete(id);
    setFlights((current) => current.filter((f) => f.id !== id));
  }, []);

  /** Resolves when the courier lands (immediately with reduced motion). */
  const fly = useCallback((from: Element | null, to: Element | null, label: string) => {
    if (!from || !to || prefersReducedMotion()) return Promise.resolve();
    const id = ++seq.current;
    const flight: Flight = {
      id,
      label,
      from: from.getBoundingClientRect(),
      to: to.getBoundingClientRect(),
    };
    return new Promise<void>((resolve) => {
      resolvers.current.set(id, resolve);
      setFlights((current) => [...current, flight]);
    });
  }, []);

  useEffect(() => {
    const pending = resolvers.current;
    return () => {
      pending.forEach((resolve) => resolve());
      pending.clear();
    };
  }, []);

  const layer = (
    <div aria-hidden="true">
      {flights.map((flight) => (
        <FlightItem key={flight.id} flight={flight} onDone={done} />
      ))}
    </div>
  );

  return { fly, layer };
}
