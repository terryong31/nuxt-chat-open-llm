# 0008 — Fine-tune the checkpoint for tool-call compliance

Accepted · 2026-08-02

## Context

[ADR 0007](0007-tool-calling-in-the-engine.md) made tool calling work end to
end: the engine renders `[AVAILABLE_TOOLS]`, parses `[TOOL_CALLS]`, and the
gateway executes the call. The protocol is correct. The model's use of it is
not.

Measured on 20 held-out prompts at temperature 0 — new phrasings on new
subjects, none of them in any training set:

| condition | web_search | rag_search | no-call | total |
| --- | --- | --- | --- | --- |
| no system prompt | 1/8 | 1/4 | 8/8 | 10/20 |
| `Be concise.` | 2/8 | 1/4 | 8/8 | 11/20 |

The shape matters more than the total. Abstention is perfect and recall is 2–3
of 12: the model does not over-call, it under-calls, badly. A user asking "who
is the current CEO of OpenAI" gets a confident answer from 2024 instead of a
search.

Prompt engineering has no headroom left. ADR 0007 measured that persona framing
or any instruction about the shape of the answer suppresses the marker
entirely, which is why `SYSTEM_PROMPT` is two words. Pushing harder on the
prompt is the one lever already known to backfire.

## Decision

Supervised LoRA fine-tune, in `packages/finetune`, served through
`LLM_ADAPTER_PATH`. Training data is rendered by the engine's own
`_mistral_instruct`, so the format trained on cannot drift from the format
served — training against a hand-written approximation would teach the model
something subtly different from what it is asked to produce, which is the class
of bug being fixed.

## Rejected

| Option | Why not |
| --- | --- |
| Reinforcement learning | The original request. `mlx-lm` ships no PPO/GRPO/DPO trainer, so this means writing one — and the target here is a known-correct string format. RL earns its cost when the target is a preference nobody can write down; here the correct output can simply be written down, which is what SFT consumes. |
| A more insistent system prompt | ADR 0007's table: the prompts that push hardest toward tools are precisely the ones that suppress the marker |
| Swap in a tool-tuned checkpoint | Abandons the premise. The project exists to run a state space model |
| Full fine-tune | 7B on 16 GB. LoRA trains 0.031% of parameters (2.24M) and peaks at 5.8 GB |
| Teach tool calls only | Tried at a 3:1 call-to-no-call ratio; it learned to search the web to reverse a string |

## Consequences

Same 20 prompts, same seed, temperature 0:

| condition | metric | base | +LoRA |
| --- | --- | --- | --- |
| no system prompt | recall (web+rag) | 2/12 | **11/12** |
| | abstention (coding) | 8/8 | **8/8** |
| | total | 10/20 | **19/20** |
| `Be concise.` | recall (web+rag) | 3/12 | **10/12** |
| | abstention (coding) | 8/8 | **8/8** |
| | total | 11/20 | **18/20** |

Val loss 1.680 → 0.204 over 300 iterations, under one epoch of 354 examples.

- **Abstention held at 8/8.** This was the risk, not the recall. A model taught
  to call tools learns to call them for everything; the 1.28:1 call-to-no-call
  ratio and the 106 coding examples exist to prevent exactly that, and the
  measurement confirms they did.

- **LoRA's default scale is unsafe on a state space model.** `mlx-lm` defaults
  to `scale: 20.0`, which drives training to NaN within ~40 iterations here.
  The cause is architectural, not a bad checkpoint: LoRA lands on
  `mixer.in_proj`, whose output is split into `gate`, `conv_input` and `dt` —
  the SSM's *time step* — and `ssm_update` then exponentiates it against
  `A_log`. A transformer's `q_proj` feeds a bounded softmax and forgives a
  large perturbation; `dt` feeds an exponential and does not.

  Diagnosis, not guesswork: the forward and backward passes are clean at step 0
  (loss 1.607, zero NaN gradients), and `max|logit|` stays flat at ~30 until the
  step it becomes NaN — it never approaches fp16's 65504. The overflow is inside
  the recurrence, not at the output.

  | config | adapts `in_proj` | scale | result |
  | --- | --- | --- | --- |
  | mlx-lm defaults | yes | 20.0 | diverged at iter 25 |
  | lowered scale | yes | 2.0 | stable, loss ~0.2 |
  | `out_proj` only | no | 20.0 | stable, loss ~0.6–1.1 |

  The third row is the control that confirms the diagnosis — skipping `in_proj`
  makes scale 20 safe — but it learns visibly worse, because it can only rescale
  the block's output and never its routing. So the fix is a smaller perturbation
  to `in_proj`, not avoiding it.

- **Hyperparameters live in `lora.yaml`, not the Makefile.** CLI flags override
  the config file, so a stray flag would silently win over a value whose comment
  explains why it must be what it is.

- **The adapter's scale is recorded in `adapter_config.json` and re-applied at
  load.** Serving at a different scale than training would multiply every
  adapted output by the ratio; that this is automatic is worth knowing rather
  than rediscovering.

- **Coding answers lost their prose, and that is traceable to the dataset.**
  Mean answer length on 5 held-out coding questions, no tools offered, fell 960
  → 673 characters. Reading them, the drop is preamble rather than capability:
  base spends its budget on "Sure, here's a simple implementation of…" and then
  emits a broken, half-finished `LRUCache`, while the adapter skips the preamble
  and produces a complete working one — *longer* on that prompt, not shorter.
  Prose answers to conceptual questions ("process versus thread") are unaffected.

  The cause is the training data: the 106 plain examples are bare code blocks
  with no explanation, so the model learned that a coding answer *is* a code
  block. If the explanation is wanted back, the fix is in `dataset.py`, not in
  the hyperparameters. Left as is for now — this checkpoint's prose was mostly
  filler — but it is a behaviour change, not a free win.

  (Both models emit occasional garbage tokens — `self enthusiaste`,
  `def get(self. key)`. That is the 4-bit quantization, present before and after.)

- **Confident recall still beats the tool.** "What did the Fed decide about
  interest rates" is answered from memory in both conditions, before and after —
  the base says rates were left unchanged, the adapter says they rose 75 basis
  points, and both are invented. Fine-tuning raised the rate at which the model
  *reaches* for a tool; it did not teach the model which of its own beliefs are
  stale. That is a different problem and would need a different instrument.

- Evaluation is scored through the engine's own `ToolCallSplitter`, so "is this
  a tool call" means in the eval exactly what it means in production, bare-JSON
  recovery path included.

## What this evidence does not cover

The 2/12 → 11/12 swing is far too large to be noise. Most of the rest of the
table is smaller than the error bars, and the numbers should not be read as
more than they are.

- **n = 20**, so 12 recall prompts and 8 abstention prompts. The gap between
  the two system-prompt conditions is a single prompt and means nothing; the
  only supported claim is that both beat base.
- **The training data and the eval share an author.** They are held out in the
  sense of not appearing in training, not in the sense of being independent.
  Some of the recall gain may be the model learning one person's idea of how an
  information-seeking question is phrased. Prompts drawn from real usage would
  be the honest test.
- **No hard abstention cases.** All 8 are unambiguous coding questions. The
  place over-calling would surface is questions that only sound time-sensitive
  — "is FastAPI faster than Flask", "what's the current best practice for X" —
  and none were tested, so 8/8 is weaker evidence than it looks.
- **Tool *selection* only.** 49 training examples teach answering *from* tool
  results, and the eval stops at the first hop. A regression in grounded
  answering — the failure that produced "Brazil" when the results said "Spain" —
  would be invisible here.
- **Temperature 0**, while the engine samples at 0.7 by default.
