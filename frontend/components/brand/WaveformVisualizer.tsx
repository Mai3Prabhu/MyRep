"use client";

import React from "react";
import { RepState } from "./RepAvatar";

interface WaveformVisualizerProps {
  active?: boolean;
  state?: RepState;
  className?: string;
  barCount?: number;
}

export default function WaveformVisualizer({
  active = false,
  state = "idle",
  className = "",
  barCount = 14,
}: WaveformVisualizerProps) {
  // Delays and heights for natural waveform variance
  const bars = Array.from({ length: barCount }, (_, i) => i);

  const getBarColor = (index: number) => {
    if (state === "listening") {
      return index % 3 === 0 ? "bg-teal-400" : "bg-teal-500";
    }
    if (state === "speaking") {
      return index % 2 === 0 ? "bg-rep-lavender-500" : "bg-rep-lavender-600";
    }
    if (state === "thinking") {
      return "bg-amber-400";
    }
    return "bg-slate-300";
  };

  return (
    <div
      className={`flex items-center justify-center gap-1 h-9 ${className}`}
      aria-hidden="true"
    >
      {bars.map((id) => {
        const isAnimated = active || state === "listening" || state === "speaking";
        return (
          <span
            key={id}
            className={`w-1 rounded-full ${isAnimated ? "rep-wave-on" : "h-1"} ${getBarColor(id)}`}
          />
        );
      })}
    </div>
  );
}
