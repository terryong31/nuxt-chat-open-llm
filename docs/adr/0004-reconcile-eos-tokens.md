# 0004 — Reconcile the checkpoint's EOS tokens at load

Accepted · 2026-08-01

## Context

`mlx-community/Mamba-Codestral-7B-v0.1-4bit` ships a `config.json` declaring
`eos_token_id: 0` (`<unk>`). The real end-of-turn token is `2` (`</s>`).

`mlx_lm` builds its stop set from `config.json` and lets it override whatever
the tokenizer declares. Nothing ever matches, so the model emits a literal
`</s>` as text and runs to `max_tokens` on every single reply. It looks like a
bad model. It is a wrong integer in someone else's upload.

## Decision

`_reconcile_eos_tokens` in `engine/mlx_engine.py` unions the tokenizer's own
`eos_token_id` back into the stop set at load, and logs a warning when it has
to.

## Rejected

| Option | Why not |
| --- | --- |
| Patch the local Hugging Face cache | Silently lost on re-download |
| Fork and re-upload the checkpoint | Maintenance burden for a one-line data bug |
| Hardcode `{2}` | Breaks the moment `LLM_MODEL_ID` changes |

## Consequences

- **Union, not replace** — a checkpoint with several legitimate stop tokens
  keeps all of them.
- The startup warning is the point. Pointing at another community conversion
  tells you immediately whether it has the same defect.
- `LLM_EXTRA_EOS_TOKENS` extends the set without code changes.
- Measured before and after: replies went from `finish_reason: length` at
  `max_tokens` to `stop` at 2 tokens, and 5 concurrent requests went 8.8 s →
  3.0 s. The server was doing an order of magnitude of wasted work.

Generalised: bad output means suspect the prompt format and the stop tokens
before suspecting the model.
