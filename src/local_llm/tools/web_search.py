import json
from typing import List, Dict, Any
from ddgs import DDGS
import trafilatura

# --- Tool Schemas (OpenAI / Qwen Format) ---

WEB_SEARCH_TOOL_DEFINITION: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the live web using DuckDuckGo for current events, facts, technical syntax, release notes, documentation, or any up-to-date information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query keywords."
                }
            },
            "required": ["query"]
        }
    }
}

WEB_FETCH_TOOL_DEFINITION: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": "Fetch and extract clean text and main content from a specific web page URL (e.g. from search results).",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The complete HTTP/HTTPS URL of the web page to fetch."
                }
            },
            "required": ["url"]
        }
    }
}


def perform_web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Executes a DuckDuckGo search and returns formatted title, url, snippet dictionaries.
    """
    try:
        ddgs = DDGS()
        results = ddgs.text(query, max_results=max_results)
        formatted: List[Dict[str, str]] = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            })
        return formatted
    except Exception as e:
        return [{"error": f"Search error: {str(e)}"}]


def perform_web_fetch(url: str) -> str:
    """
    Fetches a web page by URL and extracts clean readable text via Trafilatura.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return f"Error: Unable to download content from {url}"
        extracted = trafilatura.extract(
            downloaded,
            include_links=True,
            include_images=False,
            output_format="txt"
        )
        if not extracted:
            return f"Notice: No readable text extracted from {url}"
        # Limit extracted body size for LLM context
        return extracted[:3000]
    except Exception as e:
        return f"Error fetching {url}: {str(e)}"
