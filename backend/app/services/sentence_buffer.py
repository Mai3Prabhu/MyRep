"""Turn streamed model text into complete spoken sentences.

Incomplete fragments stay in the buffer. A sentence is emitted only at a
boundary (punctuation followed by whitespace, or a newline) or when the
stream ends and flush() is called.
"""

from __future__ import annotations

_ABBREVIATIONS = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "sr",
    "jr",
    "st",
    "vs",
    "etc",
    "eg",
    "ie",
}


class SentenceBuffer:
    def __init__(self) -> None:
        self._buf = ""

    def push(self, delta: str) -> list[str]:
        if not delta:
            return []
        self._buf += delta
        ready: list[str] = []
        while True:
            end = self._boundary_end()
            if end is None:
                end = self._clause_end()
            if end is None:
                break
            sentence = self._buf[:end].strip()
            self._buf = self._buf[end:]
            if sentence:
                ready.append(sentence)
        return ready

    def flush(self) -> str | None:
        text = self._buf.strip()
        self._buf = ""
        return text or None

    def _clause_end(self) -> int | None:
        """Start speech at a clause instead of waiting for a long first sentence."""
        text = self._buf
        if len(text) < 80:
            return None
        for mark in (", ", "; "):
            idx = text.find(mark)
            if 40 <= idx <= 220:
                return idx + len(mark)
        if len(text) >= 180:
            cut = text.rfind(" ", 40, 180)
            if cut > 40:
                return cut + 1
        return None

    def _boundary_end(self) -> int | None:
        text = self._buf
        index = 0
        while index < len(text):
            char = text[index]
            if char == "\n":
                if text[:index].strip():
                    return index + 1
                index += 1
                continue
            if char in ".?!":
                if self._should_hold(text, index):
                    if index + 1 >= len(text):
                        return None
                    index += 1
                    continue
                if index + 1 >= len(text):
                    return None
                if text[index + 1] not in " \t\n":
                    index += 1
                    continue
                return index + 1
            index += 1
        return None

    def _should_hold(self, text: str, index: int) -> bool:
        char = text[index]
        previous = text[index - 1] if index else ""
        if char == "." and previous.isdigit():
            nxt = text[index + 1] if index + 1 < len(text) else ""
            return nxt == "" or nxt.isdigit()
        if char != ".":
            return False
        start = index
        while start > 0 and text[start - 1].isalpha():
            start -= 1
        word = text[start:index].lower()
        return word in _ABBREVIATIONS or len(word) == 1
