"""DuckDuckGo web search tool for the LangGraph agent."""

import logging

from ddgs import DDGS
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return a summary of results.

    Use this tool when the user asks about current events, facts that may have
    changed after the model's training cutoff, or anything that requires up-to-date
    information from the internet.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 5).

    Returns:
        A formatted string with search results including titles, URLs and snippets.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return f"No results found for query: {query}"

        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            href = r.get("href", "")
            body = r.get("body", "")
            formatted.append(f"[{i}] {title}\nURL: {href}\n{body}")

        return "\n\n".join(formatted)

    except Exception as e:  # noqa: BLE001
        logger.warning("DuckDuckGo search failed: %s", e)
        return f"Search failed: {e!s}"
