"""Separating a tool call out of a stream of plain text.

Mistral checkpoints announce a tool call inline, as a `[TOOL_CALLS]` marker
followed by a JSON array. Nothing upstream frames it, so the engine has to find
it in the token stream itself.

The awkward part is that the marker arrives in pieces. `stream_generate` yields
whatever the detokenizer has settled on, so `[TOOL_CALLS]` can straddle two
chunks and a naive `"[TOOL_CALLS]" in chunk` check misses it -- leaking `[TOOL`
into the visible answer and then treating the rest as prose. That is the same
shape as the EOS bug in ADR 0004: a special token that survives as literal text
and is silently wrong rather than loud.

So text is released only once it cannot still turn out to be the start of the
marker. Nothing here imports mlx or fastapi; it is a string problem, and keeping
it that way is what makes it testable without loading 3.8 GB.
"""

from __future__ import annotations

import json
import logging
import secrets
import string

from .base import ToolCall

log = logging.getLogger(__name__)

MARKER = "[TOOL_CALLS]"

# Mistral v3 wants a 9-character alphanumeric call id. The model usually omits
# the id entirely, but OpenAI's wire format requires one, so we mint it here.
_ID_ALPHABET = string.ascii_letters + string.digits
_ID_LENGTH = 9


def new_call_id() -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LENGTH))


def _partial_marker_len(text: str) -> int:
    """How many trailing characters could still be the start of MARKER.

    `"...[TOOL"` returns 5, so those characters are held back instead of being
    shown to the user and then contradicted.
    """
    limit = min(len(text), len(MARKER) - 1)
    for size in range(limit, 0, -1):
        if text.endswith(MARKER[:size]):
            return size
    return 0


def parse_tool_calls(payload: str) -> list[ToolCall]:
    """Parse the JSON array that follows the marker.

    Tolerates trailing text after the array -- the model sometimes keeps
    talking, and `raw_decode` stops at the end of the first complete value.
    Returns [] on anything malformed; the caller falls back to plain text.
    """
    text = payload.strip()
    if not text:
        return []

    try:
        decoded, _ = json.JSONDecoder().raw_decode(text)
    except ValueError:
        log.warning("unparseable tool call payload: %.120s", text)
        return []

    if isinstance(decoded, dict):
        decoded = [decoded]
    if not isinstance(decoded, list):
        return []

    calls: list[ToolCall] = []
    for entry in decoded:
        if not isinstance(entry, dict):
            continue
        # Mistral emits {"name", "arguments"}; be lenient about the OpenAI
        # {"function": {...}} nesting in case a checkpoint uses it.
        fn = entry.get("function") if isinstance(entry.get("function"), dict) else entry
        name = fn.get("name")
        if not name:
            continue
        arguments = fn.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append(
            ToolCall(
                id=entry.get("id") or new_call_id(), name=name, arguments=arguments
            )
        )
    return calls


class ToolCallSplitter:
    """Feeds text through, holding back anything that might start a marker.

    Usage is `feed()` per chunk, then `finish()` once the model stops.
    """

    def __init__(self) -> None:
        self._pending = ""  # held back: could be a partial marker
        self._payload: list[str] = []  # everything after the marker
        self._found = False

    @property
    def found_tool_call(self) -> bool:
        return self._found

    def feed(self, chunk: str) -> str:
        """Return the portion of `chunk` that is safe to show now."""
        if self._found:
            self._payload.append(chunk)
            return ""

        self._pending += chunk
        index = self._pending.find(MARKER)
        if index != -1:
            self._found = True
            visible = self._pending[:index]
            self._payload.append(self._pending[index + len(MARKER) :])
            self._pending = ""
            return visible

        hold = _partial_marker_len(self._pending)
        if hold == 0:
            visible, self._pending = self._pending, ""
            return visible
        visible = self._pending[:-hold]
        self._pending = self._pending[-hold:]
        return visible

    def finish(self) -> tuple[str, list[ToolCall]]:
        """End of stream. Returns (remaining visible text, tool calls).

        A partial marker that never completed is real text after all, so it is
        released here rather than swallowed. If the payload does not parse, the
        marker and payload are handed back as text: a malformed call should look
        like a bad answer, not a missing one.
        """
        if not self._found:
            trailing, self._pending = self._pending, ""
            return trailing, []

        payload = "".join(self._payload)
        calls = parse_tool_calls(payload)
        if not calls:
            return MARKER + payload, []
        return "", calls
