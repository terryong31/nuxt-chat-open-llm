import re
import json
import uuid
from typing import List, Dict, Any


def parse_tool_calls(text: str) -> List[Dict[str, Any]]:
    """
    Extracts tool calls from Qwen/OpenAI XML format:
    <tool_call>
    <function=web_search>
    <parameter=query>
    python FastAPI
    </parameter>
    </function>
    </tool_call>
    Also supports JSON-inside-tool-call format:
    <tool_call>
    {"name": "web_search", "arguments": {"query": "python FastAPI"}}
    </tool_call>
    """
    tool_calls: List[Dict[str, Any]] = []

    # 1. XML Format: <tool_call><function=name>...</function></tool_call>
    xml_matches = re.findall(
        r"<tool_call>\s*<function=([a-zA-Z0-9_-]+)>\s*(.*?)\s*</function>\s*</tool_call>",
        text,
        re.DOTALL,
    )
    for func_name, params_block in xml_matches:
        param_matches = re.findall(
            r"<parameter=([a-zA-Z0-9_-]+)>\s*(.*?)\s*</parameter>",
            params_block,
            re.DOTALL,
        )
        args: Dict[str, Any] = {}
        for p_name, p_val in param_matches:
            val_clean = p_val.strip()
            try:
                args[p_name] = json.loads(val_clean)
            except Exception:
                args[p_name] = val_clean

        if not args and params_block.strip():
            # Fallback: single unnamed string parameter
            if func_name == "web_search":
                args = {"query": params_block.strip()}
            elif func_name == "web_fetch":
                args = {"url": params_block.strip()}

        tool_calls.append({
            "tool_name": func_name,
            "tool_call_id": f"call_{uuid.uuid4().hex[:8]}",
            "args": args,
        })

    # 2. JSON Format inside <tool_call>...</tool_call>
    if not tool_calls:
        json_matches = re.findall(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
        for jm in json_matches:
            try:
                data = json.loads(jm)
                func_name = data.get("name") or data.get("function")
                args = data.get("arguments") or data.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"query": args}
                if func_name:
                    tool_calls.append({
                        "tool_name": func_name,
                        "tool_call_id": f"call_{uuid.uuid4().hex[:8]}",
                        "args": args,
                    })
            except Exception:
                pass

    return tool_calls
