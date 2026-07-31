"""Turning a message list into something the tokenizer accepts.

Chat formatting is a property of the checkpoint, not of the API, which is why
it sits beside the engine instead of in a route. Point the server at a
different model and only this file's fallback path is at risk.
"""

from __future__ import annotations

from collections.abc import Sequence

from .base import Message


def build_prompt(tokenizer, messages: Sequence[Message]) -> str | list[int]:
    """Prefer the checkpoint's own chat template; fall back to Mistral-instruct.

    When a template exists, `apply_chat_template` returns token ids, which
    `stream_generate` accepts directly. Passing ids avoids a detokenize /
    retokenize round trip and, more importantly, avoids re-encoding special
    tokens that the template just emitted.
    """
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            [{"role": m.role, "content": m.as_text} for m in messages],
            add_generation_prompt=True,
        )
    return _mistral_instruct(messages)


def _mistral_instruct(messages: Sequence[Message]) -> str:
    """The `[INST]` format used by Mistral and Codestral checkpoints.

    Two things here are easy to get wrong:

    No leading "<s>". These tokenizers set `add_bos_token=True`, so writing one
    literally would emit a second BOS token and put the model off-distribution.

    Mistral has no system role. A system prompt is folded into the first user
    turn, which is the convention the instruct tuning was trained on -- passing
    it as its own turn produces noticeably worse instruction following.
    """
    pending_system = "\n\n".join(m.as_text for m in messages if m.role == "system")

    parts: list[str] = []
    for message in messages:
        if message.role == "system":
            continue
        if message.role == "user":
            content = message.as_text
            if pending_system:
                content = f"{pending_system}\n\n{content}"
                pending_system = ""
            parts.append(f"[INST] {content} [/INST]")
        else:
            # The trailing EOS closes the assistant turn; the tokenizer parses
            # "</s>" back into the special token when it encodes this string.
            parts.append(f" {message.as_text}</s>")

    return "".join(parts)
