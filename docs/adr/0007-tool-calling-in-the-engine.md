# 0007 — The engine reports tool calls, the gateway runs them

Accepted · 2026-08-02

## Context

`server/api` bound `web_search` and `rag_search` to the model, the graph had a
`run_tools` node, and the system prompt told the model both tools existed. None
of it could fire. `server/llm` had no tool support at any layer: no `tools`
field on the request (so pydantic discarded the schemas on every call), no
`"tool"` role (so a result could not be sent back), no `tool_calls` on the
response (so a call could not be returned), and the string "tool" appeared
nowhere in `prompts.py`. `should_use_tools` therefore always routed straight to
`save_reply`, and the prompt advertised something structurally unreachable.

The first reading of this was that the checkpoint could not call tools. That was
wrong, and worth recording because it nearly led to deleting the feature instead
of building it. The tokenizer carries Mistral's full tool vocabulary —
`[TOOL_CALLS]`, `[AVAILABLE_TOOLS]`, `[/AVAILABLE_TOOLS]`, `[TOOL_RESULTS]`,
`[/TOOL_RESULTS]` — and given a correctly formatted prompt the model emits:

```
[TOOL_CALLS] [{"name": "web_search", "arguments": {"query": "weather in Paris"}}]
```

The earlier probe failed only because `[AVAILABLE_TOOLS]` was placed inside the
`[INST]` block rather than before it. Position is not cosmetic here.

## Decision

Tool calling is a **protocol capability of the engine**, not an agent feature.

`server/llm` renders offered tools into the prompt, detects `[TOOL_CALLS]` in
the token stream, parses the JSON, and returns OpenAI-shaped `tool_calls`. It
never executes anything. `server/api` decides which tools to offer, runs the
one the model picked, and feeds the result back as a `tool` turn.

That line keeps [0006](0006-move-the-bff-into-a-python-gateway.md) intact: the
agent loop stays in the gateway. It also protects
[0003](0003-serialize-generation.md) — a tool executing inside the engine would
hold the single generation worker for the length of a web request, which is the
one thing that ADR forbids.

Detection lives in `engine/toolcalls.py`, which imports neither mlx nor FastAPI.
The marker arrives split across chunks, so text is released only once it can no
longer turn out to be the start of one.

## Rejected

| Option | Why not |
| --- | --- |
| Execute tools inside `server/llm` | Pins the only generation worker on a network call and inverts `api → engine` |
| Parse the code-form call the model sometimes writes (`web_search(query=…)`) | Non-standard, unparseable in general, and rewards the behaviour we want to suppress |
| Stream `tool_calls` as argument fragments, as OpenAI does | The engine only knows the call once the JSON array is complete; fragments would be invented, and every client accepts one whole chunk |
| Drop the tools instead, and the prompt text with them | The capability was one layer of plumbing away; deleting it would have been the expensive mistake |
| Depend on `mistral-common` at runtime for formatting | A heavy dependency to emit four constant markers |

## Consequences

- **Compliance is uneven on this checkpoint**, and that is a model property, not
  a bug to chase. Measured at temperature 0: "what is the weather in Paris"
  produces a proper call, "who won the 2026 World Cup final" produces Python
  prose. The question matters more than the tool count — weather is the
  canonical function-calling example in Mistral's training data. A system-prompt
  nudge lifted one case in three. A tool-tuned checkpoint works unchanged.
- `arguments` must be serialised as a JSON **string**, matching OpenAI.
  langchain-openai parses it back; emitting an object binds nothing and reports
  no error.
- The model omits the call `id`, so the engine mints a 9-character alphanumeric
  one to satisfy both Mistral's convention and OpenAI's requirement.
- A malformed payload degrades to visible text rather than raising, so a bad
  call reads as a bad answer instead of a silent absence.
- `LLMEngine` gains `supports_tools`, mirroring `supports_images`. A future
  engine that cannot do this says so rather than ignoring the field, which is
  the failure this ADR exists to end.
