"""Live check: one Bulbul socket, three sentences, flush after each.

Prints message types and sizes only. Does not print the API key or audio.
"""

from __future__ import annotations

import asyncio
import json
import time

from app.services import sarvam_service

SENTENCES = [
    "Hello, this is the first sentence.",
    "Here is the second sentence.",
    "And this is the third sentence.",
]


def _summarize(message: dict) -> dict:
    kind = message.get("type")
    if kind == "audio":
        data = message.get("data") or {}
        audio = data.get("audio") or ""
        return {
            "type": "audio",
            "content_type": data.get("content_type"),
            "b64_chars": len(audio) if isinstance(audio, str) else 0,
        }
    if kind == "event":
        data = message.get("data") or {}
        return {"type": "event", "event_type": data.get("event_type")}
    if kind == "error":
        return {"type": "error"}
    return {"type": kind or "unknown"}


async def _recv_until_final(ws, timeout: float) -> list[dict]:
    events: list[dict] = []
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        remaining = deadline - time.perf_counter()
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(remaining, 0.1))
        except asyncio.TimeoutError:
            events.append({"type": "timeout"})
            break
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            events.append({"type": "non_json"})
            continue
        if not isinstance(message, dict):
            events.append({"type": "non_object"})
            continue
        item = _summarize(message)
        events.append(item)
        if item.get("type") == "event" and item.get("event_type") == "final":
            break
        if item.get("type") == "error":
            break
    return events


def _open(ws) -> bool:
    code = getattr(ws, "close_code", None)
    return code is None


async def sequential() -> None:
    print("MODE sequential_wait_for_final")
    ws = await sarvam_service.websockets.connect(
        sarvam_service._tts_url(),
        **sarvam_service._connect_kwargs(sarvam_service._headers()),
        ping_interval=20,
        ping_timeout=20,
        max_size=2**23,
    )
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "config",
                    "data": {
                        "model": "bulbul:v3",
                        "language_code": "en-IN",
                        "speaker": "shubh",
                        "speech_sample_rate": "24000",
                        "output_audio_codec": "linear16",
                        "min_buffer_size": 30,
                    },
                }
            )
        )
        for index, sentence in enumerate(SENTENCES, start=1):
            started = time.perf_counter()
            send_error = None
            try:
                await ws.send(json.dumps({"type": "text", "data": {"text": sentence}}))
                await ws.send(json.dumps({"type": "flush"}))
            except Exception as exc:
                send_error = type(exc).__name__
            events = [] if send_error else await _recv_until_final(ws, 20)
            audio = sum(1 for item in events if item.get("type") == "audio")
            finals = sum(
                1
                for item in events
                if item.get("type") == "event" and item.get("event_type") == "final"
            )
            print(
                json.dumps(
                    {
                        "sentence": index,
                        "chars": len(sentence),
                        "send_error": send_error,
                        "elapsed_ms": int((time.perf_counter() - started) * 1000),
                        "audio_messages": audio,
                        "final_events": finals,
                        "socket_open_after": _open(ws),
                        "events": events,
                    }
                )
            )
            if send_error or not _open(ws):
                break
    finally:
        try:
            await ws.close()
        except Exception:
            pass


async def overlapped() -> None:
    print("MODE production_send_without_waiting")
    session = await sarvam_service.open_pcm_tts()
    heard: list[int] = []

    async def collect() -> None:
        async for chunk in session.chunks():
            heard.append(len(chunk.get("audio") or ""))

    task = asyncio.create_task(collect())
    started = time.perf_counter()
    send_error = None
    try:
        for sentence in SENTENCES:
            await session.send_sentence(sentence)
    except Exception as exc:
        send_error = type(exc).__name__
    await session.finish()
    await task
    print(
        json.dumps(
            {
                "send_error": send_error,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "pcm_chunks": len(heard),
                "flushes": session._flush_count,
                "finals": session._final_count,
                "b64_chars": heard,
            }
        )
    )


async def main() -> None:
    if not sarvam_service.configured():
        print("SARVAM_NOT_CONFIGURED")
        return
    await sequential()
    await overlapped()


if __name__ == "__main__":
    asyncio.run(main())
