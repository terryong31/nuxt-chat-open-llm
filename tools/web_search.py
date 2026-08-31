from typing import Any
from ddgs import DDGS
import trafilatura


WEB_SEARCH_TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information, news, documentation, or reference links using DuckDuckGo.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The concise search query or keywords to look up on the web."
                }
            },
            "required": ["query"]
        }
    }
}

WEB_FETCH_TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": "Fetch and read the full webpage body content from a specific URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The absolute HTTP/HTTPS URL of the webpage to fetch."
                }
            },
            "required": ["url"]
        }
    }
}


def perform_web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """
    Executes a web search query using DuckDuckGo (ddgs).
    Returns a list of structured source items with title, url, and snippet.
    """
    clean_query = query.strip().strip("\"'")
    if not clean_query:
        return []

    results: list[dict[str, str]] = []
    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(clean_query, max_results=max_results))
            if raw_results:
                for item in raw_results:
                    title = item.get("title", "").strip()
                    url = item.get("href", "").strip()
                    snippet = item.get("body", "").strip()
                    if not url:
                        continue

                    results.append({
                        "title": title or url,
                        "url": url,
                        "snippet": snippet,
                    })
    except Exception as e:
        print(f"Error performing web search for '{query}': {e}")

    return results


def perform_web_fetch(url: str, max_chars: int = 4000) -> dict[str, str]:
    """
    Fetches and extracts readable text from a webpage URL using Trafilatura.
    """
    clean_url = url.strip().strip("\"'")
    if not clean_url:
        return {"url": url, "content": "Error: Empty URL provided."}

    try:
        downloaded = trafilatura.fetch_url(clean_url)
        if downloaded:
            extracted = trafilatura.extract(downloaded, include_links=False, include_tables=True)
            if extracted and extracted.strip():
                return {
                    "url": clean_url,
                    "content": extracted.strip()[:max_chars]
                }
    except Exception as e:
        print(f"Error fetching URL '{clean_url}': {e}")

    return {"url": clean_url, "content": f"Failed to extract readable content from {clean_url}."}
