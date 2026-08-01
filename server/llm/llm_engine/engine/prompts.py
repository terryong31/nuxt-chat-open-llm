"""Turning a message list into something the tokenizer accepts.

Chat formatting is a property of the checkpoint, not of the API, which is why
it sits beside the engine instead of in a route. Point the server at a
different model and only this file's fallback path is at risk.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from .base import Message, ToolSpec


def build_prompt(
    tokenizer,
    messages: Sequence[Message],
    tools: Sequence[ToolSpec] = (),
) -> str | list[int]:
    """Prefer the checkpoint's own chat template; fall back to Mistral-instruct.

    When a template exists, `apply_chat_template` returns token ids, which
    `stream_generate` accepts directly. Passing ids avoids a detokenize /
    retokenize round trip and, more importantly, avoids re-encoding special
    tokens that the template just emitted.
    """
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            [{"role": m.role, "content": m.as_text} for m in messages],
            tools=[_openai_tool(t) for t in tools] or None,
            add_generation_prompt=True,
        )
    return _mistral_instruct(messages, tools)


def _openai_tool(tool: ToolSpec) -> dict:
    """The envelope Mistral was trained to see inside `[AVAILABLE_TOOLS]`."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _mistral_instruct(
    messages: Sequence[Message],
    tools: Sequence[ToolSpec] = (),
) -> str:
    """The `[INST]` format used by Mistral and Codestral checkpoints.

    Three things here are easy to get wrong:

    No leading "<s>". These tokenizers set `add_bos_token=True`, so writing one
    literally would emit a second BOS token and put the model off-distribution.

    Mistral has no system role. A system prompt is folded into the first user
    turn, which is the convention the instruct tuning was trained on -- passing
    it as its own turn produces noticeably worse instruction following.

    Tools go immediately before the *last* user turn, not at the top. Position
    is not cosmetic: with the block anywhere else this checkpoint ignores the
    protocol and writes the call out as Python instead, which is how the first
    attempt at this failed.
    """
    pending_system = "\n\n".join(m.as_text for m in messages if m.role == "system")
    tools_block = (
        f"[AVAILABLE_TOOLS] {json.dumps([_openai_tool(t) for t in tools])} "
        "[/AVAILABLE_TOOLS]"
        if tools
        else ""
    )
    last_user = max(
        (i for i, m in enumerate(messages) if m.role == "user"),
        default=-1,
    )

    parts: list[str] = []
    for index, message in enumerate(messages):
        if message.role == "system":
            continue

        if message.role == "user":
            content = message.as_text
            if pending_system:
                content = f"{pending_system}\n\n{content}"
                pending_system = ""
            if tools_block and index == last_user:
                parts.append(tools_block)
            parts.append(f"[INST] {content} [/INST]")

        elif message.role == "tool":
            result = json.dumps(
                {"call_id": message.tool_call_id or "", "content": message.as_text}
            )
            parts.append(f"[TOOL_RESULTS] {result} [/TOOL_RESULTS]")

        elif message.tool_calls:
            # An assistant turn that asked for tools. Replayed so the model can
            # see its own call alongside the result that came back.
            calls = json.dumps(
                [
                    {"name": c.name, "arguments": c.arguments, "id": c.id}
                    for c in message.tool_calls
                ]
            )
            parts.append(f"[TOOL_CALLS] {calls}</s>")

        else:
            # The trailing EOS closes the assistant turn; the tokenizer parses
            # "</s>" back into the special token when it encodes this string.
            parts.append(f" {message.as_text}</s>")

    return "".join(parts)
