"""Mistral `[INST]` rendering, including where the tools block goes.

Position is the whole point of these tests. With `[AVAILABLE_TOOLS]` anywhere
other than immediately before the final `[INST]`, this checkpoint ignores the
protocol and writes the call out as Python instead -- which is exactly how the
first attempt at tool calling failed.
"""

import json

from llm_engine.engine.base import Message, ToolCall, ToolSpec
from llm_engine.engine.prompts import _mistral_instruct

SEARCH = ToolSpec(
    name="web_search",
    description="Search the internet.",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}},
)


def user(text: str) -> Message:
    return Message.text("user", text)


def assistant(text: str) -> Message:
    return Message.text("assistant", text)


def test_single_turn_has_no_leading_bos():
    """add_bos_token=True already emits one; a literal <s> would be a second."""
    assert _mistral_instruct([user("hi")]) == "[INST] hi [/INST]"


def test_multi_turn_closes_assistant_turns_with_eos():
    prompt = _mistral_instruct([user("a"), assistant("b"), user("c")])
    assert prompt == "[INST] a [/INST] b</s>[INST] c [/INST]"


def test_system_folds_into_the_first_user_turn():
    """Mistral has no system role; a separate turn degrades instruction following."""
    prompt = _mistral_instruct([Message.text("system", "Be terse."), user("hi")])
    assert prompt == "[INST] Be terse.\n\nhi [/INST]"


def test_tools_are_absent_when_none_are_offered():
    assert "AVAILABLE_TOOLS" not in _mistral_instruct([user("hi")])


def test_tools_sit_immediately_before_the_instruction():
    prompt = _mistral_instruct([user("weather?")], [SEARCH])
    assert prompt.startswith("[AVAILABLE_TOOLS] ")
    assert prompt.endswith("[/AVAILABLE_TOOLS][INST] weather? [/INST]")


def test_tools_attach_to_the_last_user_turn_not_the_first():
    """The block belongs to the live question, not the top of the transcript."""
    prompt = _mistral_instruct([user("a"), assistant("b"), user("c")], [SEARCH])
    assert prompt.index("[AVAILABLE_TOOLS]") > prompt.index("[INST] a [/INST]")
    assert prompt.endswith("[/AVAILABLE_TOOLS][INST] c [/INST]")


def test_tool_payload_is_the_openai_function_envelope():
    prompt = _mistral_instruct([user("x")], [SEARCH])
    body = prompt.split("[AVAILABLE_TOOLS] ")[1].split(" [/AVAILABLE_TOOLS]")[0]
    assert json.loads(body) == [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the internet.",
                "parameters": SEARCH.parameters,
            },
        }
    ]


def test_a_tool_exchange_replays_as_calls_then_results():
    """The follow-up request must show the model its own call and the answer."""
    call = ToolCall(id="abc123xyz", name="web_search", arguments={"query": "paris"})
    prompt = _mistral_instruct(
        [
            user("weather?"),
            Message(role="assistant", content=(), tool_calls=(call,)),
            Message(
                role="tool",
                content=(),
                tool_call_id="abc123xyz",
            ),
        ]
    )
    assert "[TOOL_CALLS] " in prompt
    assert prompt.endswith("[/TOOL_RESULTS]")
    assert '"call_id": "abc123xyz"' in prompt
