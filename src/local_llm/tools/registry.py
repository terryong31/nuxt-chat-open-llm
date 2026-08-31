from typing import List, Dict, Any
from local_llm.tools.web_search import (
    WEB_SEARCH_TOOL_DEFINITION,
    WEB_FETCH_TOOL_DEFINITION,
    perform_web_search,
    perform_web_fetch,
)

# Registered tool definitions for LLM tool calling
TOOLS_REGISTRY: List[Dict[str, Any]] = [
    WEB_SEARCH_TOOL_DEFINITION,
    WEB_FETCH_TOOL_DEFINITION,
]

__all__ = [
    "TOOLS_REGISTRY",
    "WEB_SEARCH_TOOL_DEFINITION",
    "WEB_FETCH_TOOL_DEFINITION",
    "perform_web_search",
    "perform_web_fetch",
]
