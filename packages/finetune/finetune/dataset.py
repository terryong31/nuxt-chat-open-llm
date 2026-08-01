"""Build LoRA training data for tool calling.

The checkpoint knows the `[TOOL_CALLS]` format -- it produces it correctly when
the prompt is short. What it lacks is robustness: add a system prompt and a
second tool and it drops the marker, writes the call as Python, or invents a
tool that was never offered (ADR 0007). That is a format-compliance problem, and
supervised fine-tuning is the direct instrument for it.

Every example is rendered by `_mistral_instruct`, the same function the engine
serves with. Training on a hand-written approximation of the format would teach
the model something subtly different from what it is asked to produce at
inference, and that gap is exactly the bug being fixed.

Three behaviours are taught together, because teaching only the first would
produce a model that calls tools for everything:

1. information-seeking question  -> a tool call, nothing else
2. coding question               -> a direct answer, no tool call
3. question + tool results       -> an answer grounded in those results

mlx-lm's `CompletionsDataset` applies a chat template, and this tokenizer has
none, so output uses the `{"text": ...}` form and carries the full rendered
sequence.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from llm_engine.engine.base import Message, ToolCall, ToolSpec
from llm_engine.engine.prompts import _mistral_instruct

WEB_SEARCH = ToolSpec(
    name="web_search",
    description="Search the web using DuckDuckGo and return a summary of results.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
)
RAG_SEARCH = ToolSpec(
    name="rag_search",
    description="Search the user's document store for relevant context.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
TOOLS = [WEB_SEARCH, RAG_SEARCH]

# Varied so the model learns the *shape* of an information need, not a phrasing.
WEB_TEMPLATES = [
    "who won {topic}",
    "can you search online for {topic}",
    "what is the latest news about {topic}",
    "look up {topic}",
    "search the web for {topic}",
    "what happened with {topic} recently",
    "find current information on {topic}",
    "what's the latest on {topic}",
    "any updates on {topic}?",
    "check online what {topic} is",
]
WEB_TOPICS = [
    "the 2026 World Cup final",
    "the latest Nuxt release",
    "Apple's earnings",
    "the Python 3.14 release notes",
    "the current price of Bitcoin",
    "today's weather in Tokyo",
    "the newest MLX version",
    "the Formula 1 championship standings",
    "recent SpaceX launches",
    "the latest Rust release",
    "current AWS outages",
    "the UEFA final result",
    "new Postgres features",
    "the latest iPhone announcement",
    "current mortgage rates",
    "recent earthquakes in Japan",
]
RAG_TEMPLATES = [
    "what do my documents say about {topic}",
    "check my notes for {topic}",
    "search my uploaded files for {topic}",
    "what did I write about {topic}",
    "find {topic} in my knowledge base",
    "look through my documents for {topic}",
]
RAG_TOPICS = [
    "the caching strategy",
    "our deployment process",
    "the API rate limits",
    "the onboarding checklist",
    "last quarter's roadmap",
    "the incident postmortem",
    "our testing conventions",
    "the database schema",
    "the security review",
    "the migration plan",
]

# Coding questions must stay tool-free, or the model learns to search for
# everything. Answers are short on purpose: the target is routing, not prose.
CODING = [
    (
        "write a python function that reverses a string",
        "```python\ndef reverse_string(s: str) -> str:\n    return s[::-1]\n```",
    ),
    (
        "how do I read a csv file in python",
        "```python\nimport csv\n\nwith open('data.csv') as f:\n    rows = list(csv.DictReader(f))\n```",
    ),
    (
        "write a function to check if a number is prime",
        "```python\ndef is_prime(n: int) -> bool:\n    if n < 2:\n        return False\n    return all(n % i for i in range(2, int(n**0.5) + 1))\n```",
    ),
    (
        "show me a typescript debounce function",
        "```typescript\nfunction debounce<T extends (...a: never[]) => void>(fn: T, ms: number) {\n  let t: ReturnType<typeof setTimeout>\n  return (...a: Parameters<T>) => {\n    clearTimeout(t)\n    t = setTimeout(() => fn(...a), ms)\n  }\n}\n```",
    ),
    ("how do I reverse a list in place in python", "```python\nitems.reverse()\n```"),
    (
        "write a rust function that sums a vector",
        "```rust\nfn sum(v: &[i64]) -> i64 {\n    v.iter().sum()\n}\n```",
    ),
    (
        "give me a sql query for the top 10 customers by revenue",
        "```sql\nSELECT customer_id, SUM(amount) AS revenue\nFROM orders\nGROUP BY customer_id\nORDER BY revenue DESC\nLIMIT 10;\n```",
    ),
    (
        "how do I deep copy a dict in python",
        "```python\nimport copy\n\nclone = copy.deepcopy(original)\n```",
    ),
    (
        "write a go function that reverses a slice of ints",
        "```go\nfunc reverse(s []int) {\n\tfor i, j := 0, len(s)-1; i < j; i, j = i+1, j-1 {\n\t\ts[i], s[j] = s[j], s[i]\n\t}\n}\n```",
    ),
    (
        "what's the python idiom for a default dict value",
        "```python\nfrom collections import defaultdict\n\ncounts = defaultdict(int)\n```",
    ),
    (
        "write a bash one liner to count files in a directory",
        "```bash\nls -1 | wc -l\n```",
    ),
    (
        "how do I format a date in javascript",
        "```javascript\nnew Date().toISOString().slice(0, 10)\n```",
    ),
]

# Grounded answers: the exact failure where the model was handed the winner and
# said "no current updates available", then hallucinated a different team.
GROUNDED = [
    (
        "who won the 2026 World Cup",
        "2026 World Cup winner",
        "[1] 2026 FIFA World Cup - Wikipedia\nURL: https://en.wikipedia.org/wiki/2026_FIFA_World_Cup\nThe tournament began on June 11, 2026, and concluded on July 19 with Spain winning the championship for the second time.",
        "Spain won the 2026 World Cup, beating the tournament's other finalist on July 19.",
    ),
    (
        "what is the latest version of Nuxt",
        "latest Nuxt version",
        "[1] Nuxt 4.0 released\nURL: https://nuxt.com/blog/v4\nNuxt 4.0 is now stable, with a new directory structure and faster cold starts.",
        "Nuxt 4.0 is the latest stable release, bringing a new directory structure and faster cold starts.",
    ),
    (
        "what's the newest MLX version",
        "newest MLX version",
        "[1] mlx releases\nURL: https://github.com/ml-explore/mlx/releases\nv0.29.0 is the most recent release, adding faster quantized matmul kernels.",
        "The newest MLX release is v0.29.0, which adds faster quantized matmul kernels.",
    ),
    (
        "how much is Bitcoin right now",
        "bitcoin price",
        "[1] Bitcoin price\nURL: https://coinmarketcap.com/currencies/bitcoin/\nBitcoin is trading at $71,240, up 2.1% over the last 24 hours.",
        "Bitcoin is trading at $71,240, up 2.1% in the last 24 hours.",
    ),
    (
        "what happened in the F1 championship",
        "F1 championship standings",
        "[1] F1 standings\nURL: https://formula1.com/standings\nVerstappen leads the drivers' championship with 310 points, 24 ahead of Norris.",
        "Verstappen leads the drivers' championship on 310 points, 24 clear of Norris.",
    ),
    (
        "any recent earthquakes in Japan",
        "recent earthquakes Japan",
        "[1] Recent earthquakes\nURL: https://earthquake.usgs.gov\nA magnitude 5.2 earthquake struck off the coast of Honshu on 30 July 2026. No tsunami warning was issued.",
        "A magnitude 5.2 earthquake struck off the coast of Honshu on 30 July 2026, with no tsunami warning issued.",
    ),
]

CALL_ID = "Xk29fPqrT"


def _tool_call_example(question: str, tool: str, query: str) -> str:
    """Question in, `[TOOL_CALLS]` out, and nothing else."""
    prompt = _mistral_instruct([Message.text("user", question)], TOOLS)
    call = json.dumps([{"name": tool, "arguments": {"query": query}}])
    return f"{prompt}[TOOL_CALLS] {call}</s>"


def _plain_example(question: str, answer: str) -> str:
    """Tools are on offer and deliberately not taken."""
    prompt = _mistral_instruct([Message.text("user", question)], TOOLS)
    return f"{prompt} {answer}</s>"


def _grounded_example(question: str, query: str, result: str, answer: str) -> str:
    """A full exchange: call, result, then an answer that uses the result."""
    call = ToolCall(id=CALL_ID, name="web_search", arguments={"query": query})
    prompt = _mistral_instruct(
        [
            Message.text("user", question),
            Message(role="assistant", content=(), tool_calls=(call,)),
            Message(role="tool", content=(), tool_call_id=CALL_ID),
        ],
        TOOLS,
    )
    # `_mistral_instruct` renders the tool turn with empty content; splice the
    # real payload in so the model sees a realistic result to read from.
    prompt = prompt.replace('"content": ""', f'"content": {json.dumps(result)}')
    return f"{prompt} {answer}</s>"


def build(seed: int = 0) -> list[str]:
    rng = random.Random(seed)
    rows: list[str] = []

    for template in WEB_TEMPLATES:
        for topic in WEB_TOPICS:
            question = template.format(topic=topic)
            rows.append(_tool_call_example(question, "web_search", topic))

    for template in RAG_TEMPLATES:
        for topic in RAG_TOPICS:
            question = template.format(topic=topic)
            rows.append(_tool_call_example(question, "rag_search", topic))

    # Repeated so routing-to-no-tool is not drowned out. Some skew toward
    # calling is wanted -- under-calling is the failure being fixed -- but at
    # 3:1 the model learns to search for "reverse a string", which is worse.
    for _ in range(10):
        for question, answer in CODING:
            rows.append(_plain_example(question, answer))

    for _ in range(9):
        for question, query, result, answer in GROUNDED:
            rows.append(_grounded_example(question, query, result, answer))

    rng.shuffle(rows)
    return rows


def main() -> None:
    rows = build()
    out = Path(__file__).resolve().parents[1] / "data"
    out.mkdir(exist_ok=True)

    split = int(len(rows) * 0.9)
    parts = {"train": rows[:split], "valid": rows[split:]}
    for name, chunk in parts.items():
        path = out / f"{name}.jsonl"
        with path.open("w") as f:
            for text in chunk:
                f.write(json.dumps({"text": text}) + "\n")
        print(f"{path}: {len(chunk)} examples")


if __name__ == "__main__":
    main()
