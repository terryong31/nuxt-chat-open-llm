"""A tiny streaming client, for poking the server by hand.

Speaks the same SSE protocol as any OpenAI client, so it doubles as a worked
example of what the Nuxt app has to do:

    python test.py
"""

import json

import httpx

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = httpx.Timeout(10.0, read=300.0)  # generation is slow; connecting is not


def stream_reply(client: httpx.Client, messages: list[dict]) -> str:
    """Print tokens as they arrive and return the assembled reply."""
    parts: list[str] = []

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={"messages": messages, "stream": True},
    ) as response:
        if response.status_code != 200:
            response.read()  # a streamed body is not loaded until asked for
            print(f"\n[{response.status_code}] {response.text}")
            return ""

        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line.removeprefix("data: ")
            if payload == "[DONE]":
                break

            chunk = json.loads(payload)
            if "error" in chunk:
                print(f"\n[error] {chunk['error']['message']}")
                break

            delta = chunk["choices"][0]["delta"].get("content")
            if delta:
                parts.append(delta)
                print(delta, end="", flush=True)

    print()
    return "".join(parts)


def main() -> None:
    # Kept across turns, which is the point of the messages array -- the old
    # {"query": ...} endpoint could not express a second turn at all.
    messages: list[dict] = []

    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        while True:
            try:
                prompt = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not prompt:
                continue
            if prompt in {"/exit", "/quit"}:
                return
            if prompt == "/reset":
                messages.clear()
                print("(history cleared)")
                continue

            messages.append({"role": "user", "content": prompt})
            reply = stream_reply(client, messages)
            if reply:
                messages.append({"role": "assistant", "content": reply})
            else:
                messages.pop()  # don't poison history with a failed turn


if __name__ == "__main__":
    main()
