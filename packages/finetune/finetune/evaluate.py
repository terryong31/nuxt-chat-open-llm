"""Measure tool-call compliance, base checkpoint versus adapter.

The number that matters is not loss. It is: when the user asks something that
needs a search, does a parseable `[TOOL_CALLS]` come back -- and when they ask
to reverse a string, does one stay away? Loss can fall while both get worse,
because the model can learn the format on the training topics and generalise
nothing.

So every prompt here is held out: new phrasings on new subjects, none of them
in `dataset.py`. Memorising the training set scores zero.

Two conditions are run, because production and training disagree. The gateway
sends a system prompt ("Be concise.") and the training data has none. The
checkpoint is known to drop the marker under exactly that kind of prompt
pressure (server/llm/CLAUDE.md), so measuring only the clean case would report
a win the running system never sees.

Classification goes through the engine's own `ToolCallSplitter`, so what counts
as a tool call here is precisely what counts as one in production -- including
the bare-JSON recovery path. A call the splitter rejects is not a call.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass

from llm_engine.engine.base import Message
from llm_engine.engine.mlx_engine import _reconcile_eos_tokens
from llm_engine.engine.prompts import _mistral_instruct
from llm_engine.engine.toolcalls import ToolCallSplitter

# pyrefly: ignore [missing-import]
from mlx_lm import load, stream_generate

# pyrefly: ignore [missing-import]
from mlx_lm.sample_utils import make_sampler

from .dataset import TOOLS

# What the gateway actually sends on the tool-selection pass.
SYSTEM_PROMPT = "Be concise."

# Greedy: the question is what the model believes, not what it can be sampled
# into. A rate measured at temperature 0.7 mixes the two.
TEMPERATURE = 0.0

# Enough to finish a call and show whether prose follows; not enough to wait
# through a full code answer we are not grading.
MAX_TOKENS = 96


@dataclass(frozen=True)
class Case:
    prompt: str
    expect: str | None  # tool name, or None for "should not call"


CASES = [
    # Information-seeking. None of these topics or phrasings are in the
    # training data.
    Case("who is the current CEO of OpenAI", "web_search"),
    Case("what's the score in the Lakers game tonight", "web_search"),
    Case("tell me the news in Malaysia today", "web_search"),
    Case("how much does a Tesla Model 3 cost right now", "web_search"),
    Case("when is the next Starship flight", "web_search"),
    Case("is Cloudflare having an outage at the moment", "web_search"),
    Case("what did the Fed decide about interest rates", "web_search"),
    Case("which team is top of the Premier League", "web_search"),
    # Document-store questions.
    Case("what does my documentation say about retries", "rag_search"),
    Case("pull up my notes on the vendor contract", "rag_search"),
    Case("do I have anything written down about error budgets", "rag_search"),
    Case("search my files for the Q3 budget", "rag_search"),
    # Coding. A tool call here is a regression, and the one this fine-tune is
    # most likely to cause.
    Case("write a python decorator that times a function", None),
    Case("how do I merge two dicts in python", None),
    Case("explain what a closure is in javascript", None),
    Case("write a sql query to find duplicate emails", None),
    Case("what's the difference between let and const", None),
    Case("implement binary search in python", None),
    Case("how do I catch an exception in rust", None),
    Case("write a regex that matches an email address", None),
]

TOOL_NAMES = [t.name for t in TOOLS]


def _classify(model, tokenizer, prompt: str) -> tuple[str | None, str]:
    """Generate, then ask the production splitter what it sees.

    Returns (tool name or None, visible text).
    """
    splitter = ToolCallSplitter(TOOL_NAMES)
    visible: list[str] = []
    for response in stream_generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=MAX_TOKENS,
        sampler=make_sampler(temp=TEMPERATURE),
    ):
        visible.append(splitter.feed(response.text))

    trailing, calls = splitter.finish()
    visible.append(trailing)
    text = "".join(visible).strip()
    return (calls[0].name if calls else None), text


def _run(model, tokenizer, system: str | None) -> dict:
    results = []
    for case in CASES:
        messages = []
        if system:
            messages.append(Message.text("system", system))
        messages.append(Message.text("user", case.prompt))
        prompt = _mistral_instruct(messages, TOOLS)

        got, text = _classify(model, tokenizer, prompt)
        results.append(
            {
                "prompt": case.prompt,
                "expect": case.expect,
                "got": got,
                "ok": got == case.expect,
                "text": text[:160],
            }
        )
    return {"results": results}


def _summarise(results: list[dict]) -> dict[str, str]:
    """Three rates, because one aggregate would hide the regression.

    Over-calling on coding questions is the failure mode of this fine-tune, so
    it gets its own line rather than being averaged away against recall.
    """
    buckets: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    for row in results:
        kind = "no-call" if row["expect"] is None else row["expect"]
        totals[kind] += 1
        buckets[kind] += int(row["ok"])

    out = {}
    for kind in ("web_search", "rag_search", "no-call"):
        if totals[kind]:
            out[kind] = f"{buckets[kind]}/{totals[kind]}"
    out["total"] = f"{sum(buckets.values())}/{sum(totals.values())}"
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="mlx-community/Mamba-Codestral-7B-v0.1-4bit")
    parser.add_argument("--adapter", default=None, help="adapter dir, or omit for base")
    parser.add_argument("--json", dest="json_out", default=None)
    args = parser.parse_args()

    model, tokenizer = load(args.model, adapter_path=args.adapter)
    # Without this the checkpoint never stops -- config.json names the wrong
    # EOS (ADR 0004), and every reply runs to MAX_TOKENS with `</s>` as text.
    _reconcile_eos_tokens(tokenizer, [])

    label = args.adapter or "base"
    report = {}
    for name, system in (
        ("no system prompt", None),
        ("with system prompt", SYSTEM_PROMPT),
    ):
        run = _run(model, tokenizer, system)
        summary = _summarise(run["results"])
        report[name] = {"summary": summary, "results": run["results"]}

        print(f"\n=== {label} / {name} ===")
        for key, value in summary.items():
            print(f"  {key:<12} {value}")
        for row in run["results"]:
            if not row["ok"]:
                print(
                    f"  MISS  {row['prompt'][:46]:<46} "
                    f"expect={row['expect']} got={row['got']}"
                )

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
