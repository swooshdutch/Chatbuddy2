NO_RESULTS_TEXT = "No search results found."
UNAVAILABLE_TEXT = "Web search is currently unavailable."


def duckduckgo_search_context(query: str, max_results: int = 3) -> tuple[str, str]:
    """
    Retrieve top DuckDuckGo results and format them for model context.

    Returns a tuple of (text, status), where status is one of:
    - "ok"
    - "no_results"
    - "unavailable"
    """
    query = (query or "").strip()
    if not query:
        return NO_RESULTS_TEXT, "no_results"

    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return NO_RESULTS_TEXT, "no_results"

        context = "Here is some current information from the web to help answer the user:\n\n"
        for idx, res in enumerate(results, 1):
            context += f"Result {idx}:\n"
            context += f"Title: {res.get('title')}\n"
            context += f"Content: {res.get('body')}\n"
            context += f"Source: {res.get('href')}\n\n"

        return context.strip(), "ok"
    except Exception as e:
        print(f"[ChatBuddy] DuckDuckGo Search Error for query {query!r}: {e}")
        return UNAVAILABLE_TEXT, "unavailable"


def get_duckduckgo_context(query: str, max_results: int = 3) -> str:
    """
    Backward-compatible wrapper that returns only the formatted context text.
    """
    text, _status = duckduckgo_search_context(query, max_results=max_results)
    return text
