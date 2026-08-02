# finetune — LoRA recipes for the local checkpoint

Training data and commands for teaching `mlx-community/Mamba-Codestral-7B-v0.1-4bit`
to emit tool calls reliably. See [ADR 0007](../../docs/adr/0007-tool-calling-in-the-engine.md)
for why that is needed: the checkpoint knows the `[TOOL_CALLS]` format but
applies it unevenly, dropping the marker as soon as a system prompt and a
second tool are in play.

This is supervised fine-tuning, not reinforcement learning. `mlx-lm` ships no
PPO/GRPO/DPO trainer, and the problem is format compliance against a
known-correct target — which is what SFT is for. RL would be the instrument if
the target were a preference nobody can write down.

## Commands

Every target loads the 3.8 GB checkpoint, so **stop `make llm` first** — 16 GB
does not hold an engine and a trainer at once.

```shell
make finetune-data        # regenerate data/{train,valid}.jsonl
make finetune             # train; writes adapters/
make finetune-eval-base   # score the base checkpoint
make finetune-eval        # score the adapter
make finetune-serve       # run the engine with the adapter applied
```

## Data

`dataset.py` generates 354 train / 40 valid examples, rendered by the engine's
own `_mistral_instruct`. That import is why this package depends on
`llm-engine`: train on a hand-written approximation of the format and the model
learns something subtly different from what it is asked to produce at
inference, which is the bug being fixed.

Three behaviours are taught together, because teaching only the first produces
a model that searches the web to reverse a string:

| Behaviour | Count | Target |
| --- | --- | --- |
| information-seeking question | 199 | a tool call, nothing else |
| coding question | 106 | a direct answer, no tool call |
| question + tool results | 49 | an answer grounded in those results |

The 1.28:1 call-to-no-call ratio is deliberate. Some skew toward calling is
wanted — under-calling is the failure being fixed — but an earlier 3:1 mix
taught it to search for "reverse a string", which is worse than the original
problem.

Output uses the `{"text": ...}` form rather than `{"prompt", "completion"}`:
mlx-lm's `CompletionsDataset` applies a chat template, and this tokenizer has
none.

## Evaluation

`evaluate.py` scores 20 held-out prompts — new phrasings on new subjects, none
of them in the training data, so memorising the training set scores zero.

Three rates are reported separately rather than as one aggregate, because
over-calling on coding questions is this fine-tune's characteristic regression
and an average would hide it behind improved recall.

Classification runs through the engine's own `ToolCallSplitter`, so "is this a
tool call" means exactly what it means in production, bare-JSON recovery path
included.

Both runs are scored **with and without a system prompt**. The training data
has none and the gateway sends `"Be concise."`; since the checkpoint is known
to drop the marker under precisely that pressure, scoring only the clean case
would report a win the running system never sees.

### Measured

300 iterations, val loss 1.680 → 0.204:

| condition | metric | base | +LoRA |
| --- | --- | --- | --- |
| no system prompt | recall (web+rag) | 2/12 | **11/12** |
| | abstention (coding) | 8/8 | **8/8** |
| `Be concise.` | recall (web+rag) | 3/12 | **10/12** |
| | abstention (coding) | 8/8 | **8/8** |

Abstention holding at 8/8 is the result to care about. Recall was always going
to move; the open question was whether it moved by making the model call tools
indiscriminately, and it did not.

One failure survives in both conditions and is worth knowing about: *"what did
the Fed decide about interest rates"* is answered from memory rather than
searched, before and after. The fine-tune raised how often the model reaches
for a tool; it did not teach it which of its own beliefs have expired.
