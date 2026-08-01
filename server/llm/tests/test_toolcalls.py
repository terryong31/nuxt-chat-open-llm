"""The tool-call splitter, exercised without loading a checkpoint.

`ToolCallSplitter` is pure string handling precisely so these can run in
milliseconds on any machine. The chunk boundaries below are the interesting
part: a real stream never hands you `[TOOL_CALLS]` in one piece.
"""

from llm_engine.engine.toolcalls import MARKER, ToolCallSplitter, parse_tool_calls

PAYLOAD = '[{"name": "web_search", "arguments": {"query": "weather in Paris"}}]'


def _run(chunks: list[str]) -> tuple[str, list]:
    """Feed chunks through and return (visible text, tool calls)."""
    splitter = ToolCallSplitter()
    visible = "".join(splitter.feed(c) for c in chunks)
    trailing, calls = splitter.finish()
    return visible + trailing, calls


def test_plain_text_passes_through_untouched():
    text, calls = _run(["Hello", ", ", "world!"])
    assert text == "Hello, world!"
    assert calls == []


def test_tool_call_arriving_in_one_chunk():
    text, calls = _run([f"{MARKER} {PAYLOAD}"])
    assert text == ""
    assert [c.name for c in calls] == ["web_search"]
    assert calls[0].arguments == {"query": "weather in Paris"}


def test_marker_split_across_every_boundary():
    """The regression this class exists for.

    A naive substring check sees no marker in any single chunk and leaks
    `[TOOL` into the answer. Splitting at all 12 positions covers every way
    the detokenizer can land mid-marker.
    """
    for cut in range(1, len(MARKER)):
        text, calls = _run([MARKER[:cut], MARKER[cut:] + " " + PAYLOAD])
        assert text == "", f"leaked visible text when split at {cut}: {text!r}"
        assert [c.name for c in calls] == ["web_search"]


def test_marker_split_one_character_at_a_time():
    text, calls = _run(list(f"{MARKER} {PAYLOAD}"))
    assert text == ""
    assert [c.name for c in calls] == ["web_search"]


def test_text_before_a_tool_call_is_kept():
    text, calls = _run(["Let me look. ", MARKER, " ", PAYLOAD])
    assert text == "Let me look. "
    assert len(calls) == 1


def test_bracket_text_that_never_becomes_a_marker_is_released():
    """Held-back characters are text after all, and must not be swallowed."""
    text, calls = _run(["see [TOO", "LBOX] for details"])
    assert text == "see [TOOLBOX] for details"
    assert calls == []


def test_partial_marker_at_end_of_stream_is_released():
    text, calls = _run(["done [TOOL"])
    assert text == "done [TOOL"
    assert calls == []


def test_malformed_payload_degrades_to_text():
    """A broken call should read as a bad answer, not a missing one."""
    text, calls = _run([f"{MARKER} not json at all"])
    assert calls == []
    assert text == f"{MARKER} not json at all"


def test_ids_are_generated_when_the_model_omits_them():
    """This checkpoint emits no id, but OpenAI's wire format requires one."""
    calls = parse_tool_calls(PAYLOAD)
    assert len(calls[0].id) == 9
    assert calls[0].id.isalnum()


def test_supplied_id_is_preserved():
    calls = parse_tool_calls('[{"name": "f", "arguments": {}, "id": "abc123xyz"}]')
    assert calls[0].id == "abc123xyz"


def test_trailing_prose_after_the_array_is_ignored():
    calls = parse_tool_calls(f"{PAYLOAD}\nI will search for that.")
    assert [c.name for c in calls] == ["web_search"]


def test_arguments_as_json_string_are_decoded():
    calls = parse_tool_calls('[{"name": "f", "arguments": "{\\"q\\": 1}"}]')
    assert calls[0].arguments == {"q": 1}


def test_openai_style_function_nesting_is_accepted():
    calls = parse_tool_calls('[{"function": {"name": "f", "arguments": {"q": 1}}}]')
    assert calls[0].name == "f"
    assert calls[0].arguments == {"q": 1}
