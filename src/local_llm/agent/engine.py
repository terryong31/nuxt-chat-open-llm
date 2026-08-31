import time
import json
from typing import Generator, Any, List, Dict
from mlx_lm import stream_generate
from mlx_lm.sample_utils import make_sampler, make_logits_processors
from local_llm.tools.registry import TOOLS_REGISTRY
from local_llm.agent.parser import parse_tool_calls
from local_llm.agent.graph import react_graph


def stream_graph_chat(
    model: Any,
    tokenizer: Any,
    messages_payload: List[Dict[str, Any]],
    thinking_budget: int = 0,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    top_p: float = 0.9,
    repetition_penalty: float = 1.1,
) -> Generator[str, None, None]:
    """
    Deterministic Two-Phase Agent Engine:
    - Phase 1: Reasoning & Parallel Tool Selection
    - Phase 2: Tool Execution (web_search / web_fetch)
    - Phase 3: Guaranteed Final Markdown Synthesis Pass
    """
    sampler = make_sampler(temp=temperature, top_p=top_p)
    logits_processors = make_logits_processors(
        repetition_penalty=repetition_penalty,
        repetition_context_size=64,
    )
    tools = TOOLS_REGISTRY

    start_time = time.perf_counter()
    gen_start_time = None
    thinking_tokens = 0
    answer_tokens = 0
    prompt_tokens = 0
    prompt_tps = 0.0
    peak_mem = 0.0

    current_messages = list(messages_payload)

    # 1. System Instruction with Proactive Search
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
        base_prompt = "\n".join(f"{m['role']}: {m['content']}" for m in current_messages) + "\nassistant:"

    in_thinking = base_prompt.endswith("<think>\n") or base_prompt.endswith("<think>")
    raw_buffer = ""
    thinking_text = ""
    accumulated_tool_text = ""
    budget_exceeded = False

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

        prompt_tokens = res.prompt_tokens
        prompt_tps = res.prompt_tps
        peak_mem = res.peak_memory
        raw_buffer += res.text

        if in_thinking:
            if "</think>" in raw_buffer:
                think_part, after_think = raw_buffer.split("</think>", 1)
                new_think = think_part[len(thinking_text):]
                if new_think:
                    thinking_tokens += 1
                    yield f"data: {json.dumps({'type': 'thinking', 'token': new_think})}\n\n"
                thinking_text = think_part
                in_thinking = False
                raw_buffer = after_think
            else:
                thinking_tokens += 1
                new_token = res.text
                thinking_text += new_token
                yield f"data: {json.dumps({'type': 'thinking', 'token': new_token})}\n\n"
                if thinking_budget > 0 and thinking_tokens >= thinking_budget:
                    budget_exceeded = True
                    break
        else:
            accumulated_tool_text += res.text
            # If the model is not calling tools and has finished thinking, stream directly as answer
            if "<tool_call>" not in accumulated_tool_text and "<function=" not in accumulated_tool_text:
                if not ("<" in accumulated_tool_text and not any(tag in accumulated_tool_text for tag in ["<tool_call>", "<function="])):
                    if len(accumulated_tool_text) > 10:
                        answer_tokens += 1
                        yield f"data: {json.dumps({'type': 'answer', 'token': accumulated_tool_text})}\n\n"
                        accumulated_tool_text = ""

    # Handle thinking budget continuation if thinking was cut short
    if budget_exceeded:
        in_thinking = False
        continued_prompt = base_prompt + thinking_text + "\n</think>\n\n"
        remaining_tokens = max(1, max_tokens - thinking_tokens)
        for res in stream_generate(
            model=model,
            tokenizer=tokenizer,
            prompt=continued_prompt,
            max_tokens=remaining_tokens,
            sampler=sampler,
            logits_processors=logits_processors,
        ):
            peak_mem = res.peak_memory
            accumulated_tool_text += res.text
            if "<tool_call>" not in accumulated_tool_text and "<function=" not in accumulated_tool_text:
                if not ("<" in accumulated_tool_text and not any(tag in accumulated_tool_text for tag in ["<tool_call>", "<function="])):
                    if len(accumulated_tool_text) > 10:
                        answer_tokens += 1
                        yield f"data: {json.dumps({'type': 'answer', 'token': accumulated_tool_text})}\n\n"
                        accumulated_tool_text = ""

    # Check for tool calls
    tool_text_to_parse = accumulated_tool_text + (raw_buffer if not in_thinking else "")
    detected_tools = parse_tool_calls(tool_text_to_parse)

    # 3. Phase 2: Execute Tool Calls via LangGraph
    if detected_tools:
        for t in detected_tools:
            yield f"data: {json.dumps({'type': 'tool_call', 'tool_name': t['tool_name'], 'tool_call_id': t['tool_call_id'], 'args': t['args']})}\n\n"

        graph_result = react_graph.invoke({"messages": current_messages, "tool_calls": detected_tools, "tool_results": []})
        tool_results = graph_result.get("tool_results", [])

        # Format context from tool results
        retrieved_context_blocks = []
        for r in tool_results:
            yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': r['tool_name'], 'tool_call_id': r['tool_call_id'], 'result': r['result']})}\n\n"
            tname = r['tool_name']
            targ = json.dumps(r.get('args', {}))
            tres = json.dumps(r.get('result', []))
            retrieved_context_blocks.append(f"Tool `{tname}` called with `{targ}` returned:\n{tres}")

        # 4. Phase 3: Guaranteed Final Synthesis Pass
        synthesize_directive = (
            f"Here is the real-time retrieved information:\n\n"
            + "\n\n---\n\n".join(retrieved_context_blocks)
            + "\n\nUsing the retrieved information above, write a complete, detailed, and comprehensive final response now."
        )

        synthesis_messages = list(current_messages)
        synthesis_messages.append({"role": "user", "content": synthesize_directive})

        try:
            synth_prompt = tokenizer.apply_chat_template(
                synthesis_messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
        except TypeError:
            synth_prompt = tokenizer.apply_chat_template(
                synthesis_messages, tokenize=False, add_generation_prompt=True
            ) + "\n</think>\n\n"

        for res in stream_generate(
            model=model,
            tokenizer=tokenizer,
            prompt=synth_prompt,
            max_tokens=max_tokens,
            sampler=sampler,
            logits_processors=logits_processors,
        ):
            peak_mem = res.peak_memory
            token_text = res.text
            # Filter out any lingering tool tags
            if "<tool_call>" in token_text or "</tool_call>" in token_text or "<function=" in token_text:
                continue
            answer_tokens += 1
            yield f"data: {json.dumps({'type': 'answer', 'token': token_text})}\n\n"

    else:
        # Flush remaining direct answer buffer if any
        if accumulated_tool_text:
            clean_token = accumulated_tool_text.replace("<tool_call>", "").replace("</tool_call>", "")
            if clean_token:
                answer_tokens += 1
                yield f"data: {json.dumps({'type': 'answer', 'token': clean_token})}\n\n"

    # 5. Emit Final Hardware Telemetry
    elapsed = time.perf_counter() - start_time
    total_tokens = thinking_tokens + answer_tokens
    gen_tps = (total_tokens / elapsed) if elapsed > 0 else 0.0

    metrics_payload = {
        "total_tokens": total_tokens,
        "thinking_tokens": thinking_tokens,
        "answer_tokens": answer_tokens,
        "generation_tps": round(gen_tps, 2),
        "elapsed_time_sec": round(elapsed, 2),
        "prompt_tokens": prompt_tokens,
        "prompt_tps": round(prompt_tps, 2),
        "peak_memory_gb": round(peak_mem, 2),
    }
    yield f"data: {json.dumps({'type': 'metrics', 'metrics': metrics_payload})}\n\n"
    yield "data: [DONE]\n\n"
