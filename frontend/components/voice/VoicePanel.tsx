"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { voiceLiveUrl } from "@/lib/api";
import { shouldShowEvidence } from "@/lib/conversationSummary";
import RepAvatar, { RepState } from "@/components/brand/RepAvatar";
import RepNavbar from "@/components/brand/RepNavbar";
import WaveformVisualizer from "@/components/brand/WaveformVisualizer";
import SourceReferences from "@/components/chat/SourceReferences";
import {
  ConversationPill,
  ConversationRail,
} from "@/components/conversation/ConversationSummaryView";
import { useConversationFairy } from "@/components/conversation/useConversationFairy";
import { AgentIntent, SourceDisplay, TurnSummary } from "@/types/chat";

/**
 * Live voice — the single canonical voice client for /profile/voice and
 * /rep/[profile_id]/voice.
 *
 * Turn protocol (mirrors backend voice_runtime):
 *   server  final{turn_id}            → this turn becomes active; mic held
 *   server  answer / audio {turn_id}  → applied only for the active turn
 *   server  turn_complete{turn_id}    → when local playback ends, send
 *   client  playback_done{turn_id}    → server returns to LISTENING; mic resumes
 *   client  interrupt{turn_id}        → stop playback now; no new agent call
 *
 * The microphone stays muted while the Rep is thinking or speaking, so the
 * Rep's own voice can never become a user turn.
 */

interface VoicePanelProps {
  profileId: string;
  profileName: string;
  visibility: "public" | "private";
  chatHref: string;
  backHref: string;
  backLabel: string;
}

function int16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function voiceDebug(): boolean {
  try {
    return window.localStorage.getItem("myrep.voiceDebug") === "1";
  } catch {
    return false;
  }
}

function vlog(event: string, detail?: Record<string, number | string | null>) {
  if (voiceDebug()) console.info("[myrep-voice]", event, detail ?? "");
}

function voiceStage(label: string, detail?: Record<string, number | string | null>) {
  console.info(`[MyRep voice] ${label}`, detail ?? "");
}

function pcm16ToFloat(bytes: Uint8Array): Float32Array {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const count = Math.floor(bytes.byteLength / 2);
  const out = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    out[i] = view.getInt16(i * 2, true) / 32768;
  }
  return out;
}

function floatToPcm16(input: Float32Array, inRate: number, outRate: number): Int16Array {
  const ratio = inRate / outRate;
  const outLen = Math.max(1, Math.floor(input.length / ratio));
  const out = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = pos - i0;
    const sample = input[i0] + (input[i1] - input[i0]) * frac;
    const clamped = Math.max(-1, Math.min(1, sample));
    out[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return out;
}

function userFacingError(err: unknown): string {
  const message = err instanceof Error ? err.message : "Something went wrong.";
  const lower = message.toLowerCase();
  if (
    lower.includes("permission") ||
    lower.includes("notallowed") ||
    lower.includes("microphone")
  ) {
    return "Microphone access is required to speak with MyRep. Please allow microphone permissions in your browser.";
  }
  return "Could not connect voice session. Please ensure your backend is online, or switch to text chat.";
}

function asSources(value: unknown): SourceDisplay[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is SourceDisplay =>
      Boolean(item) &&
      typeof item === "object" &&
      typeof (item as SourceDisplay).filename === "string" &&
      typeof (item as SourceDisplay).page_number === "number"
  );
}

interface LastAnswer {
  text: string;
  sources: SourceDisplay[];
  summary: TurnSummary | null;
  intent: AgentIntent | null;
}

export default function VoicePanel({
  profileId,
  profileName,
  visibility,
  chatHref,
  backHref,
}: VoicePanelProps) {
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<RepState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [partial, setPartial] = useState("");
  const [lastUser, setLastUser] = useState<string | null>(null);
  const [lastAgent, setLastAgent] = useState<LastAnswer | null>(null);
  const [turnActive, setTurnActive] = useState(false);

  const {
    summary,
    repState: fairyState,
    capturing,
    railRef,
    pillRef,
    flightLayer,
    capture,
    organize,
    settle,
  } = useConversationFairy(connected ? status : "idle");

  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const playCtxRef = useRef<AudioContext | null>(null);
  const playheadRef = useRef(0);
  const sourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const userCardRef = useRef<HTMLDivElement>(null);

  // Turn state. Refs, because the audio callback and socket handlers read them.
  const sessionSeqRef = useRef(0);
  const activeTurnRef = useRef<number | null>(null);
  const serverDoneTurnRef = useRef<number | null>(null);
  const micHeldRef = useRef(false);

  const frameCountRef = useRef(0);
  const lastMicAtRef = useRef(0);
  const finalAtRef = useRef(0);
  const playStartAtRef = useRef(0);
  const firstPcmAtRef = useRef(0);
  const serverMarksRef = useRef<Record<string, number>>({});
  const seenMarksRef = useRef<Set<string>>(new Set());

  const send = useCallback((payload: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
  }, []);

  const isPlaying = useCallback(() => {
    const ctx = playCtxRef.current;
    return (
      sourcesRef.current.length > 0 ||
      Boolean(ctx && playheadRef.current > ctx.currentTime + 0.02)
    );
  }, []);

  const stopPlayback = useCallback(() => {
    playheadRef.current = 0;
    const playing = sourcesRef.current;
    sourcesRef.current = [];
    for (const source of playing) {
      try {
        source.stop();
      } catch {
        /* already stopped */
      }
    }
  }, []);

  /** Report playback_done once the server finished AND local audio drained. */
  const maybeReportPlayback = useCallback(() => {
    const turnId = serverDoneTurnRef.current;
    if (turnId === null || turnId !== activeTurnRef.current || isPlaying()) return;
    serverDoneTurnRef.current = null;
    send({ type: "playback_done", turn_id: turnId });
    micHeldRef.current = false;
    setTurnActive(false);
    voiceStage("playback_done", { turn: turnId });
  }, [isPlaying, send]);

  const schedulePcm = useCallback(
    (bytes: Uint8Array, sampleRate: number) => {
      const ctx = playCtxRef.current ?? new AudioContext();
      playCtxRef.current = ctx;
      void ctx.resume();
      const floats = pcm16ToFloat(bytes);
      if (!floats.length) return;
      const buffer = ctx.createBuffer(1, floats.length, sampleRate);
      buffer.getChannelData(0).set(floats);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);
      const now = ctx.currentTime;
      const underrun = playheadRef.current > 0 && playheadRef.current < now;
      const startAt = Math.max(now + 0.05, playheadRef.current || now + 0.05);
      source.start(startAt);
      if (!playStartAtRef.current) {
        playStartAtRef.current = performance.now();
        const lookaheadMs = Math.round((startAt - now) * 1000);
        voiceStage("audio_playback_start", {
          ms_after_final_stt: finalAtRef.current
            ? Math.round(playStartAtRef.current - finalAtRef.current)
            : null,
          scheduled_lookahead_ms: lookaheadMs,
          speech_end_to_first_audible_ms: lastMicAtRef.current
            ? Math.round(playStartAtRef.current - lastMicAtRef.current) + lookaheadMs
            : null,
        });
      }
      playheadRef.current = startAt + buffer.duration;
      sourcesRef.current.push(source);
      source.onended = () => {
        // A source stopped by stopPlayback is no longer tracked: not a natural end.
        if (!sourcesRef.current.includes(source)) return;
        sourcesRef.current = sourcesRef.current.filter((item) => item !== source);
        if (!sourcesRef.current.length && playStartAtRef.current) {
          voiceStage("audio_playback_end", {
            playback_ms: Math.round(performance.now() - playStartAtRef.current),
          });
        }
        maybeReportPlayback();
      };
      vlog(underrun ? "tts_playback_underrun" : "tts_playback_scheduled", {
        bytes: bytes.byteLength,
        sampleRate,
        queue: sourcesRef.current.length,
      });
    },
    [maybeReportPlayback]
  );

  const cleanupMic = useCallback(() => {
    processorRef.current?.disconnect();
    processorRef.current = null;
    ctxRef.current?.close().catch(() => undefined);
    ctxRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const resetTurn = useCallback(() => {
    activeTurnRef.current = null;
    serverDoneTurnRef.current = null;
    micHeldRef.current = false;
    setTurnActive(false);
  }, []);

  const stop = useCallback(() => {
    stopPlayback();
    playCtxRef.current?.close().catch(() => undefined);
    playCtxRef.current = null;
    send({ type: "end" });
    wsRef.current?.close();
    wsRef.current = null;
    cleanupMic();
    resetTurn();
    setConnected(false);
    setStatus("idle");
    setBusy(false);
  }, [cleanupMic, resetTurn, send, stopPlayback]);

  /** Tap-to-interrupt: stop this answer now. Never starts another agent call. */
  const interrupt = useCallback(() => {
    const turnId = activeTurnRef.current;
    if (turnId === null) return;
    serverDoneTurnRef.current = null;
    activeTurnRef.current = null; // late messages for this turn are now stale
    stopPlayback();
    send({ type: "interrupt", turn_id: turnId });
    micHeldRef.current = false;
    setTurnActive(false);
    setStatus("listening");
    settle();
    voiceStage("voice_turn_interrupted", { turn: turnId });
  }, [send, settle, stopPlayback]);

  const stopRef = useRef(stop);
  useEffect(() => {
    stopRef.current = stop;
  }, [stop]);
  // Leaving the page ends the session and releases the microphone.
  useEffect(() => () => stopRef.current(), []);

  const handleMessage = useCallback(
    (payload: Record<string, unknown>) => {
      const kind = payload.type;
      const turnId = typeof payload.turn_id === "number" ? payload.turn_id : null;
      const forActiveTurn = turnId !== null && turnId === activeTurnRef.current;

      if (kind === "ready") {
        setConnected(true);
        setStatus("listening");
      } else if (kind === "status") {
        const state = payload.state;
        if (state === "listening") {
          setStatus("listening");
        } else if ((state === "thinking" || state === "speaking") && forActiveTurn) {
          setStatus(state);
        }
      } else if (kind === "partial" && typeof payload.text === "string") {
        if (!micHeldRef.current) setPartial(payload.text);
      } else if (kind === "final" && typeof payload.text === "string" && turnId !== null) {
        serverDoneTurnRef.current = null;
        stopPlayback();
        activeTurnRef.current = turnId;
        micHeldRef.current = true;
        setTurnActive(true);
        setPartial("");
        setLastUser(payload.text);
        setLastAgent(null);
        finalAtRef.current = performance.now();
        playStartAtRef.current = 0;
        firstPcmAtRef.current = 0;
        serverMarksRef.current = {};
        seenMarksRef.current = new Set();
        voiceStage("voice_turn_start", { turn: turnId });
        voiceStage("final_stt_received", {
          chars: payload.text.length,
          speech_end_to_final_stt_ms: lastMicAtRef.current
            ? Math.round(finalAtRef.current - lastMicAtRef.current)
            : null,
        });
        void capture(`v${sessionSeqRef.current}-${turnId}`, payload.text, () => userCardRef.current);
      } else if (kind === "answer" && typeof payload.text === "string") {
        if (!forActiveTurn) {
          vlog("stale_answer_ignored", { turn: turnId, active: activeTurnRef.current });
          return;
        }
        const text = payload.text;
        if (payload.final === true) {
          const sources = asSources(payload.sources);
          const summary = (payload.summary as TurnSummary | null) ?? null;
          const intent = (payload.intent as AgentIntent | null) ?? null;
          setLastAgent({ text, sources, summary, intent });
          organize(
            `v${sessionSeqRef.current}-${turnId}`,
            summary,
            shouldShowEvidence(sources.length, summary, intent)
          );
        } else {
          setLastAgent((prev) => ({
            text,
            sources: prev?.sources ?? [],
            summary: prev?.summary ?? null,
            intent: prev?.intent ?? null,
          }));
        }
      } else if (kind === "audio" && typeof payload.data === "string") {
        if (!forActiveTurn) {
          vlog("stale_chunk_ignored", { turn: turnId, active: activeTurnRef.current });
          return;
        }
        const bytes = Uint8Array.from(atob(payload.data), (c) => c.charCodeAt(0));
        const contentType =
          typeof payload.content_type === "string" ? payload.content_type : "audio/pcm";
        const sampleRate = typeof payload.sample_rate === "number" ? payload.sample_rate : 24000;
        if (!firstPcmAtRef.current) {
          firstPcmAtRef.current = performance.now();
          voiceStage("tts_first_chunk_received_in_browser", {
            ms_after_final_stt: finalAtRef.current
              ? Math.round(firstPcmAtRef.current - finalAtRef.current)
              : null,
            bytes: bytes.byteLength,
          });
        }
        if (contentType.includes("pcm") || contentType.includes("wav") || contentType.includes("linear")) {
          schedulePcm(bytes, sampleRate);
        }
      } else if (kind === "turn_complete") {
        if (!forActiveTurn) return;
        if (payload.awaiting_playback === true) {
          serverDoneTurnRef.current = turnId;
          maybeReportPlayback();
        } else {
          // Nothing was spoken; the server is already listening.
          micHeldRef.current = false;
          setTurnActive(false);
        }
      } else if (kind === "timing" && payload.marks && typeof payload.marks === "object") {
        if (turnId !== null && turnId !== activeTurnRef.current) return;
        const marks = payload.marks as Record<string, number>;
        const previousMarks = serverMarksRef.current;
        serverMarksRef.current = marks;
        for (const [name, ms] of Object.entries(marks)) {
          if (seenMarksRef.current.has(name) && previousMarks[name] === ms) continue;
          seenMarksRef.current.add(name);
          voiceStage(name, { ms_from_processing_start: ms });
        }
      } else if (kind === "error" && typeof payload.message === "string") {
        if (turnId !== null && !forActiveTurn) return;
        setError(payload.message);
      }
    },
    [capture, maybeReportPlayback, organize, schedulePcm, stopPlayback]
  );

  const start = useCallback(async () => {
    setError(null);
    setBusy(true);
    sessionSeqRef.current += 1;
    resetTurn();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
      streamRef.current = stream;

      const ws = new WebSocket(voiceLiveUrl(profileId, visibility));
      wsRef.current = ws;

      ws.onmessage = (event) => {
        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }
        handleMessage(payload);
      };

      ws.onerror = () => {
        setError("Voice session failed to establish. Please check your network or backend server.");
      };
      ws.onclose = () => {
        cleanupMic();
        stopPlayback();
        resetTurn();
        setConnected(false);
        setStatus("idle");
        setBusy(false);
      };

      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        const prev = ws.onerror;
        ws.onerror = () => {
          prev?.call(ws, new Event("error"));
          reject(new Error("Voice connection failed."));
        };
      });

      const audioCtx = new AudioContext({ sampleRate: 16000 });
      ctxRef.current = audioCtx;
      vlog("mic_context", { requested: 16000, actual: audioCtx.sampleRate });
      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(2048, 1, 1);
      processorRef.current = processor;
      processor.onaudioprocess = (e) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        // Muted from the final transcript until playback_done / interrupt.
        if (micHeldRef.current || isPlaying()) return;
        const input = e.inputBuffer.getChannelData(0);
        const pcm = floatToPcm16(input, audioCtx.sampleRate, 16000);
        frameCountRef.current += 1;
        lastMicAtRef.current = performance.now();
        if (frameCountRef.current === 1) {
          voiceStage("first_mic_audio", {
            inRate: audioCtx.sampleRate,
            outRate: 16000,
            samples: pcm.length,
          });
        }
        ws.send(JSON.stringify({ type: "audio", data: int16ToBase64(pcm) }));
      };
      const mute = audioCtx.createGain();
      mute.gain.value = 0;
      source.connect(processor);
      processor.connect(mute);
      mute.connect(audioCtx.destination);
    } catch (err) {
      cleanupMic();
      wsRef.current?.close();
      wsRef.current = null;
      setError(userFacingError(err));
    } finally {
      setBusy(false);
    }
  }, [cleanupMic, handleMessage, isPlaying, profileId, resetTurn, stopPlayback, visibility]);

  const headline: Partial<Record<RepState, string>> = {
    idle: "Hi, I'm Rep.",
    listening: "I'm listening.",
    thinking: "One moment.",
    happy: "Hi, I'm Rep.",
  };
  const title = busy && !connected ? "One moment." : headline[status] ?? "";
  const heroState: RepState = capturing ? "capturing" : connected ? status : "idle";
  const evidenceVisible =
    lastAgent !== null &&
    shouldShowEvidence(lastAgent.sources.length, lastAgent.summary, lastAgent.intent);

  return (
    <div className="flex h-dvh flex-col bg-[#FBF8F4]">
      <RepNavbar chatHref={chatHref} profileHref={backHref} />

      <div className="flex min-h-0 flex-1">
        <main className="relative flex flex-1 flex-col items-center overflow-y-auto px-4 py-8">
          <div
            className={`pointer-events-none absolute top-24 h-96 w-96 rounded-full blur-3xl transition-all duration-700 ${
              connected
                ? status === "listening"
                  ? "bg-teal-300/30 scale-120 animate-pulse"
                  : status === "speaking"
                  ? "bg-purple-300/30 scale-110"
                  : "bg-amber-200/20"
                : "bg-rep-lavender-200/30"
            }`}
          />

          <div className="relative z-10 my-auto flex w-full max-w-md flex-col items-center text-center">
            <div className="relative mb-6">
              <p className="sr-only">{profileName}</p>
              <RepAvatar size="hero" state={heroState} />
            </div>

            <h2 className="font-display h-10 text-4xl text-[#16161D]" aria-live="polite">
              {title}
            </h2>

            <div className="my-6 flex h-10 w-full items-center justify-center">
              <WaveformVisualizer active={connected} state={status} barCount={22} />
            </div>

            <div className="flex flex-col items-center gap-3">
              {!connected ? (
                <button
                  type="button"
                  onClick={start}
                  disabled={busy}
                  className="relative flex h-16 w-16 items-center justify-center rounded-full bg-[#16161D] text-[#F6E7A8] transition-colors hover:bg-[#2A2A33] active:scale-95 disabled:opacity-50"
                  aria-label="Start voice session"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    className="h-8 w-8 text-rep-yellow-300"
                    aria-hidden="true"
                  >
                    <path d="M8.25 4.5a3.75 3.75 0 117.5 0v8.25a3.75 3.75 0 11-7.5 0V4.5z" />
                    <path d="M6 10.5a.75.75 0 01.75.75v1.5a5.25 5.25 0 1010.5 0v-1.5a.75.75 0 011.5 0v1.5a6.751 6.751 0 01-6 6.709v2.291h3a.75.75 0 010 1.5h-7.5a.75.75 0 010-1.5h3v-2.291a6.751 6.751 0 01-6-6.709v-1.5A.75.75 0 016 10.5z" />
                  </svg>
                </button>
              ) : (
                <div className="flex items-center gap-4">
                  {turnActive && (
                    <button
                      type="button"
                      onClick={interrupt}
                      className="rep-fade-up flex h-12 items-center gap-2 rounded-full border border-[#E6DFD4] bg-white px-5 text-sm font-medium text-[#16161D] shadow-sm transition-colors hover:bg-[#F6F1EA] active:scale-95"
                      aria-label="Stop the current answer"
                    >
                      <span className="h-3 w-3 rounded-[3px] bg-[#16161D]" aria-hidden="true" />
                      Stop
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={stop}
                    className="group relative flex h-20 w-20 items-center justify-center rounded-full bg-slate-900 text-white shadow-xl transition-all hover:bg-slate-800 active:scale-95"
                    aria-label="End voice session"
                    title="End voice session"
                  >
                    <span className="absolute -inset-2 rounded-full border-2 border-red-400/40 animate-ping [animation-duration:2.5s]" />
                    <span className="h-6 w-6 rounded-md bg-red-400 transition-transform group-hover:scale-110" />
                  </button>
                </div>
              )}
              {connected && (
                <p className="text-[11px] text-[#8A8494]">
                  {turnActive ? "Tap Stop to interrupt" : "Speak whenever you're ready"}
                </p>
              )}
            </div>

            {error && (
              <div
                className="mt-6 w-full rounded-2xl border border-red-200 bg-red-50 p-4 text-left text-xs text-red-700 shadow-xs"
                role="alert"
              >
                <p className="font-semibold">Notice</p>
                <p className="mt-0.5">{error}</p>
              </div>
            )}

            {(partial || lastUser || lastAgent) && (
              <div className="mt-8 w-full space-y-2.5 text-left text-xs">
                {partial && (
                  <div className="rounded-2xl border border-slate-200 bg-white/90 p-3 text-slate-600 shadow-2xs">
                    <span className="font-bold text-teal-600">Hearing: </span>
                    <span className="italic">{partial}</span>
                  </div>
                )}

                {lastUser && !partial && (
                  <div ref={userCardRef} className="rounded-2xl bg-slate-900 p-3.5 text-white shadow-xs">
                    <span className="font-bold text-slate-400">You: </span>
                    <span>{lastUser}</span>
                  </div>
                )}

                {lastAgent && (
                  <div className="rounded-2xl border border-rep-lavender-200 bg-white p-3.5 text-slate-800 shadow-xs">
                    <span className="font-bold text-rep-teal-700">Rep: </span>
                    <span>{lastAgent.text}</span>
                    {evidenceVisible && <SourceReferences sources={lastAgent.sources} />}
                  </div>
                )}
              </div>
            )}

            <ConversationPill
              ref={pillRef}
              summary={summary}
              repState={fairyState}
              className="mt-6 w-full"
            />
          </div>
        </main>

        <ConversationRail ref={railRef} summary={summary} repState={fairyState} />
      </div>

      {flightLayer}
    </div>
  );
}
