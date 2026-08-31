import json
import re
import time
import uuid
from typing import Any, Generator
from langgraph.graph import StateGraph, END
from mlx_lm import stream_generate
from mlx_lm.sample_utils import make_sampler, make_logits_processors

from tools.web_search import (
    WEB_SEARCH_TOOL_DEFINITION,
    WEB_FETCH_TOOL_DEFINITION,
    perform_web_search,
    perform_web_fetch,
)
from agent.state import AgentState


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """
    Robustly parses tool calls from XML tags (<tool_call>, <function=...>), or JSON blocks.
    """
    tool_calls = []

    # 1. Match <function=name>...</function> or <function=name>... (with or without outer <tool_call>)
    for func_match in re.finditer(r"<function=([a-zA-Z0-9_-]+)>(.*?)(?:</function>|</tool_call>|$)", text, re.DOTALL):
        name = func_match.group(1).strip()
        params_body = func_match.group(2)
        args = {}
        for param in re.finditer(r"<parameter=([a-zA-Z0-9_-]+)>(.*?)(?:</parameter>|$)", params_body, re.DOTALL):
            param_name = param.group(1).strip()
            param_val = param.group(2).strip()
            args[param_name] = param_val

        # If no <parameter=...> tag was found, extract clean body as query or url
        if not args:
            clean_body = re.sub(r"</?[a-zA-Z0-9_=-]+>", "", params_body).strip()
            if clean_body:
                if name == "web_fetch":
                    args = {"url": clean_body}
                else:
                    args = {"query": clean_body}

        if name:
            tool_calls.append({"name": name, "args": args})

    if tool_calls:
        return tool_calls

    # 2. Match JSON format: {"name": "...", "arguments": {...}}
    json_blocks = re.findall(r"\{[\s\S]*?\}", text)
    for block in json_blocks:
        try:
            data = json.loads(block)
            name = data.get("name") or data.get("function", {}).get("name")
            args = data.get("arguments") or data.get("parameters") or data.get("function", {}).get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"query": args}
            if name:
                tool_calls.append({"name": name, "args": args})
        except Exception:
            pass

    return tool_calls


def build_react_graph():
    """
    Constructs the LangGraph ReAct state graph for the agent.
    """
    workflow = StateGraph(dict)

    def agent_node(state: dict[str, Any]) -> dict[str, Any]:
        return {"current_step": "agent"}

    def tool_node(state: dict[str, Any]) -> dict[str, Any]:
        tool_calls = state.get("tool_calls", [])
        results = []
        for tc in tool_calls:
            name = tc.get("name", "web_search")
            args = tc.get("args", {})
            if name == "web_search":
                res = perform_web_search(query=args.get("query", ""), max_results=5)
            elif name == "web_fetch":
                res = perform_web_fetch(url=args.get("url", ""))
            else:
                res = []
            results.append({"name": name, "result": res})
        return {"tool_results": results, "current_step": "tools"}

    def should_continue(state: dict[str, Any]) -> str:
        if state.get("tool_calls"):
            return "tools"
        return END

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    return workflow.compile()


# Compile graph definition
react_graph = build_react_graph()


def stream_graph_chat(
    model: Any,
    tokenizer: Any,
    messages_payload: list[dict[str, Any]],
    thinking_budget: int = 0,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    top_p: float = 0.9,
    repetition_penalty: float = 1.1,
) -> Generator[str, None, None]:
    """
    Two-Phase Deterministic Agent Engine:
    - Phase 1: Reasoning & Tool Selection (or Direct Answer)
    - Phase 2: Tool Execution (web_search / web_fetch)
    - Phase 3: Final Synthesis Pass with explicit user instruction
    """
    sampler = make_sampler(temp=temperature, top_p=top_p)
    logits_processors = make_logits_processors(
        repetition_penalty=repetition_penalty,
        repetition_context_size=64,
    )
    tools = [WEB_SEARCH_TOOL_DEFINITION, WEB_FETCH_TOOL_DEFINITION]

    start_time = time.perf_counter()
    gen_start_time = None
    thinking_tokens = 0
    answer_tokens = 0
    prompt_tokens = 0
    prompt_tps = 0.0
    peak_mem = 0.0

    current_messages = list(messages_payload)

    # 1. System Instruction
    system_instruction = (
        "You are an expert AI assistant with live web search and webpage fetching capabilities. "
        "You have access to `web_search` and `web_fetch`. "
        "Proactively use `web_search` whenever the user asks about programming languages (e.g. Mojo, Rust, Zig, Gleam, Python), "
        "frameworks, libraries, APIs, modern syntax, current events, or ambiguous technical terms to ensure 100% accurate, up-to-date facts."
    )
    if not any(m.get("role") == "system" for m in current_messages):
        current_messages.insert(0, {"role": "system", "content": system_instruction})

    # 2. Phase 1: Decision Pass (with tools)
    try:
        if thinking_budget == 0:
            try:
                base_prompt = tokenizer.apply_chat_template(
                    current_messages, tools=tools, tokenize=False, add_generation_prompt=True, enable_thinking=False
                )
            except TypeError:
                base_prompt = tokenizer.apply_chat_template(
                    current_messages, tools=tools, tokenize=False, add_generation_prompt=True
                ) + "\n</think>\n\n"
        else:
            base_prompt = tokenizer.apply_chat_template(
                current_messages, tools=tools, tokenize=False, add_generation_prompt=True
            )
    except Exception:
        base_prompt = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in current_messages) + "\nassistant:\n"

    in_thinking = prompt_has_open_think = (
        base_prompt.endswith("<think>\n") or base_prompt.endswith("<think>") or (thinking_budget > 0)
    )
    post_think_buffer = ""
    is_tool_turn = False
    flushed_direct_answer = False

    for res in stream_generate(
        model=model,
        tokenizer=tokenizer,
        prompt=base_prompt,
        max_tokens=max_tokens,
        sampler=sampler,
        logits_processors=logits_processors,
    ):
        if gen_start_time is None:
            gen_start_time = time.perf_counter()

        prompt_tokens = getattr(res, "prompt_tokens", prompt_tokens)
        prompt_tps = getattr(res, "prompt_tps", prompt_tps)
        peak_mem = getattr(res, "peak_memory", peak_mem)
        token = res.text

        # A. Thinking Phase: strictly emit to thinking stream until </think>
        if in_thinking:
            if "</think>" in token:
                parts = token.split("</think>", 1)
                if parts[0]:
                    thinking_tokens += 1
                    yield f"data: {json.dumps({'type': 'thinking', 'token': parts[0]})}\n\n"
                in_thinking = False
                after = parts[1] if len(parts) > 1 else ""
                if after:
                    post_think_buffer += after
            else:
                thinking_tokens += 1
                yield f"data: {json.dumps({'type': 'thinking', 'token': token})}\n\n"
            continue

        # B. Post-Thinking Phase: Check for Tool Invocation vs Direct Answer
        if not flushed_direct_answer and not is_tool_turn:
            post_think_buffer += token

            if "<tool_call" in post_think_buffer or "<function=" in post_think_buffer:
                is_tool_turn = True
                continue

            if len(post_think_buffer) > 25 and not any(tag in post_think_buffer for tag in ["<tool", "<func", "<par"]):
                flushed_direct_answer = True
                answer_tokens += 1
                yield f"data: {json.dumps({'type': 'answer', 'token': post_think_buffer})}\n\n"
                post_think_buffer = ""
                continue

        elif is_tool_turn:
            post_think_buffer += token
            # Continue accumulating until tool call tag is closed or generation stops
            continue

        elif flushed_direct_answer:
            answer_tokens += 1
            yield f"data: {json.dumps({'type': 'answer', 'token': token})}\n\n"

    # End of initial pass: Check if post_think_buffer had tool calls
    if not is_tool_turn and post_think_buffer:
        if "<tool_call" in post_think_buffer or "<function=" in post_think_buffer:
            is_tool_turn = True
        elif not flushed_direct_answer:
            clean_text = re.sub(r"</?[a-zA-Z0-9_=-]+>", "", post_think_buffer).strip()
            if clean_text:
                answer_tokens += 1
                yield f"data: {json.dumps({'type': 'answer', 'token': clean_text})}\n\n"

    # 3. Phase 2 & 3: Tool Execution & Final Answer Synthesis Pass
    if is_tool_turn:
        tool_calls = parse_tool_calls(post_think_buffer)
        if tool_calls:
            for tc in tool_calls:
                tool_name = tc.get("name", "web_search")
                args = tc.get("args", {})
                tool_call_id = f"call_{uuid.uuid4().hex[:8]}"

                # Emit tool_call event to UI
                yield f"data: {json.dumps({'type': 'tool_call', 'tool_name': tool_name, 'tool_call_id': tool_call_id, 'args': args})}\n\n"

                # Execute tool
                if tool_name == "web_search":
                    query = args.get("query", "")
                    raw_res = perform_web_search(query=query, max_results=5)
                    formatted_content = "\n\n".join(
                        f"Title: {r.get('title')}\nURL: {r.get('url')}\nSnippet: {r.get('snippet')}"
                        for r in raw_res
                    ) if raw_res else "No relevant search results found."
                    result_for_ui = raw_res
                elif tool_name == "web_fetch":
                    url = args.get("url", "")
                    fetch_res = perform_web_fetch(url=url)
                    formatted_content = f"URL: {url}\n\nContent:\n{fetch_res.get('content', '')}"
                    result_for_ui = [fetch_res]
                else:
                    formatted_content = "Unknown tool."
                    result_for_ui = []

                # Emit tool_result event to UI
                yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': tool_name, 'tool_call_id': tool_call_id, 'result': result_for_ui})}\n\n"

                tool_call_xml = f"<tool_call>\n<function={tool_name}>\n"
                for k, v in args.items():
                    tool_call_xml += f"<parameter={k}>\n{v}\n</parameter>\n"
                tool_call_xml += "</function>\n</tool_call>"

                current_messages.append({"role": "assistant", "content": tool_call_xml})
                current_messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": formatted_content,
                })

            # Append explicit synthesis instruction to guarantee complete markdown answer
            current_messages.append({
                "role": "user",
                "content": "Using the retrieved information above, write a complete, detailed, and comprehensive final response now."
            })

            # Phase 3: Final Answer Synthesis Pass
            try:
                synth_prompt = tokenizer.apply_chat_template(
                    current_messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
            except Exception:
                synth_prompt = base_prompt + "\nassistant:\n"

            synth_in_think = synth_prompt.endswith("<think>\n") or synth_prompt.endswith("<think>")
            rem_tokens = max(max_tokens - thinking_tokens - answer_tokens, 512)

            for res in stream_generate(
                model=model,
                tokenizer=tokenizer,
                prompt=synth_prompt,
                max_tokens=rem_tokens,
                sampler=sampler,
                logits_processors=logits_processors,
            ):
                prompt_tokens = getattr(res, "prompt_tokens", prompt_tokens)
                prompt_tps = getattr(res, "prompt_tps", prompt_tps)
                peak_mem = getattr(res, "peak_memory", peak_mem)
                token = res.text

                if synth_in_think:
                    if "</think>" in token:
                        synth_in_think = False
                    continue

                answer_tokens += 1
                yield f"data: {json.dumps({'type': 'answer', 'token': token})}\n\n"

    elapsed_time = time.perf_counter() - start_time
    gen_time = (time.perf_counter() - gen_start_time) if gen_start_time else elapsed_time
    total_tokens = thinking_tokens + answer_tokens
    gen_tps = total_tokens / gen_time if gen_time > 0 else 0.0

    metrics_payload = {
        "total_tokens": total_tokens,
        "thinking_tokens": thinking_tokens,
        "answer_tokens": answer_tokens,
        "generation_tps": round(gen_tps, 2),
        "elapsed_time_sec": round(elapsed_time, 2),
        "prompt_tokens": prompt_tokens,
        "prompt_tps": round(prompt_tps, 2),
        "peak_memory_gb": round(peak_mem, 2),
    }

    yield f"data: {json.dumps({'type': 'metrics', 'metrics': metrics_payload})}\n\n"
    yield "data: [DONE]\n\n"
