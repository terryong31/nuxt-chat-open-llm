"""The OpenAI tool-call wire shape, checked against a fake engine.

`create_app` takes its engine as a collaborator so this can run without the
3.8 GB checkpoint. What matters here is the shape langchain-openai expects --
particularly that `arguments` is a JSON *string*. Emitting an object there is
silently wrong: the request succeeds and the tool never binds.
"""

import json

import pytest
from fastapi.testclient import TestClient
from llm_engine.app import create_app
from llm_engine.config import Settings
from llm_engine.engine.base import (
    Completed,
    Delta,
    ToolCall,
    ToolCalls,
    Usage,
)

CALL = ToolCall(id="abc123xyz", name="web_search", arguments={"query": "paris"})


class FakeEngine:
    """Replays a fixed event sequence. No weights, no threads."""

    model_id = "fake-model"
    supports_images = False
    supports_tools = True

    def __init__(self, events):
        self._events = events
        self.seen_tools = None

    @property
    def is_ready(self):
        return True

    async def start(self):
        pass

    async def stop(self):
        pass

    def stats(self):
        return {}

    async def stream_chat(self, messages, params, tools=()):
        self.seen_tools = list(tools)
        for event in self._events:
            yield event


def client_for(events):
    engine = FakeEngine(events)
    app = create_app(settings=Settings(), engine=engine)
    return TestClient(app), engine


TOOL_EVENTS = [ToolCalls((CALL,)), Completed("tool_calls", Usage(1, 1))]
TEXT_EVENTS = [Delta("Hello"), Delta(" there"), Completed("stop", Usage(1, 2))]

TOOLS_BODY = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search.",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


def test_non_streaming_tool_call_shape():
    client, _ = client_for(TOOL_EVENTS)
    with client:
        body = client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        ).json()

    choice = body["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    # OpenAI sends null content alongside a call, not "".
    assert choice["message"]["content"] is None
    call = choice["message"]["tool_calls"][0]
    assert call["id"] == "abc123xyz"
    assert call["type"] == "function"
    assert call["function"]["name"] == "web_search"
    assert json.loads(call["function"]["arguments"]) == {"query": "paris"}


def test_streaming_tool_call_shape():
    client, _ = client_for(TOOL_EVENTS)
    with client:
        raw = client.post(
            "/v1/chat/completions",
            json={
                "model": "m",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        ).text

    chunks = [
        json.loads(line[6:])
        for line in raw.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    deltas = [c["choices"][0]["delta"] for c in chunks]
    tool_delta = next(d for d in deltas if "tool_calls" in d)
    call = tool_delta["tool_calls"][0]

    assert call["index"] == 0
    assert call["id"] == "abc123xyz"
    assert isinstance(call["function"]["arguments"], str)
    assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"
    assert raw.rstrip().endswith("data: [DONE]")


def test_plain_text_streaming_is_unchanged():
    """Tool support must not disturb the ordinary path."""
    client, _ = client_for(TEXT_EVENTS)
    with client:
        raw = client.post(
            "/v1/chat/completions",
            json={
                "model": "m",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        ).text

    text = "".join(
        json.loads(line[6:])["choices"][0]["delta"].get("content", "")
        for line in raw.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    )
    assert text == "Hello there"


def test_tools_reach_the_engine():
    client, engine = client_for(TOOL_EVENTS)
    with client:
        client.post(
            "/v1/chat/completions",
            json={
                "model": "m",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": TOOLS_BODY,
            },
        )
    assert [t.name for t in engine.seen_tools] == ["web_search"]


def test_tool_choice_none_withholds_the_tools():
    client, engine = client_for(TEXT_EVENTS)
    with client:
        client.post(
            "/v1/chat/completions",
            json={
                "model": "m",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": TOOLS_BODY,
                "tool_choice": "none",
            },
        )
    assert engine.seen_tools == []


@pytest.mark.parametrize(
    "message",
    [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "abc123xyz",
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "arguments": '{"query": "paris"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "abc123xyz", "content": "22C"},
    ],
)
def test_tool_turns_are_accepted_on_the_way_in(message):
    """A tool exchange must round-trip; langchain replays it on the next call."""
    client, _ = client_for(TEXT_EVENTS)
    with client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "m",
                "messages": [{"role": "user", "content": "hi"}, message],
            },
        )
    assert response.status_code == 200
