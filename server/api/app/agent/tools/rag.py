"""pgvector RAG (Retrieval-Augmented Generation) tool for the LangGraph agent.

Uses Supabase's built-in pgvector via the `match_documents` SQL function
to retrieve semantically relevant context from the user's document store.
"""

import logging

from langchain_core.tools import tool

from app.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)

# Number of embedding dimensions expected — must match what's stored in Supabase.
# Since we have no local embedding model yet, we use a mock zero-vector for retrieval.
# When an embedding model is wired in, replace _embed() below.
_EMBED_DIM = 1536


def _embed(text: str) -> list[float]:
    """Placeholder embedding function — returns a zero vector.

    Replace this with a real embedding model call (e.g. langchain_openai.OpenAIEmbeddings
    pointing at a local embedding service) when available.
    """
    logger.warning(
        "Using zero-vector embedding placeholder — RAG results will be random"
    )
    return [0.0] * _EMBED_DIM


@tool
def rag_search(query: str, user_id: str = "", match_count: int = 5) -> str:
    """Search the user's document store for context relevant to the query.

    Use this tool when the user refers to documents, files, or knowledge they have
    previously uploaded, or when additional context from their personal knowledge
    base would improve the answer quality.

    Args:
        query: The semantic search query.
        user_id: The user's UUID to scope results (leave empty to search all docs).
        match_count: Maximum number of documents to retrieve (default 5).

    Returns:
        Formatted string with the most relevant document excerpts.
    """
    supabase = get_supabase_admin()
    embedding = _embed(query)

    try:
        result = supabase.rpc(
            "match_documents",
            {
                "query_embedding": embedding,
                "match_threshold": 0.7,
                "match_count": match_count,
                "p_user_id": user_id or None,
            },
        ).execute()

        docs = result.data or []
        if not docs:
            return "No relevant documents found in your knowledge base."

        formatted = []
        for i, doc in enumerate(docs, 1):
            content = doc.get("content", "")
            similarity = doc.get("similarity", 0)
            metadata = doc.get("metadata", {})
            source = metadata.get("source", "unknown")
            formatted.append(
                f"[{i}] (similarity={similarity:.2f}, source={source})\n{content}"
            )

        return "\n\n".join(formatted)

    except Exception as e:  # noqa: BLE001
        logger.warning("RAG search failed: %s", e)
        return f"Document search failed: {e!s}"
