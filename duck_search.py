from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

NO_RESULTS_TEXT = "No search results found."
UNAVAILABLE_TEXT = "Web search is currently unavailable."


def _format_context(results: list[dict]) -> str:
    context = "Here is some current information from the web to help answer the user:\n\n"
    for idx, res in enumerate(results, 1):
        context += f"Result {idx}:\n"
        context += f"Title: {res.get('title')}\n"
        context += f"Content: {res.get('body')}\n"
        context += f"Source: {res.get('href')}\n\n"
    return context.strip()


def _html_fallback_search(query: str, max_results: int) -> tuple[str, str]:
    params = urlencode({"q": query})
    req = Request(
        f"https://html.duckduckgo.com/html/?{params}",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        },
    )

    with urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    parsed_results: list[dict] = []

    for block in soup.select(".result"):
        title_el = block.select_one(".result__title a")
        snippet_el = block.select_one(".result__snippet")
        if not title_el:
            continue

        title = title_el.get_text(" ", strip=True)
        href = title_el.get("href", "").strip()
        body = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not href:
            continue

        parsed_results.append(
            {
                "title": title,
                "body": body or "(no snippet provided)",
                "href": href,
            }
        )
        if len(parsed_results) >= max_results:
            break

    if not parsed_results:
        return NO_RESULTS_TEXT, "no_results"

    return _format_context(parsed_results), "ok"


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

        return _format_context(results), "ok"
    except Exception as e:
        print(f"[ChatBuddy] DuckDuckGo Search Error for query {query!r}: {e}")
        try:
            return _html_fallback_search(query, max_results)
        except Exception as fallback_error:
            print(
                f"[ChatBuddy] DuckDuckGo HTML fallback error for query {query!r}: "
                f"{fallback_error}"
            )
            return UNAVAILABLE_TEXT, "unavailable"


def get_duckduckgo_context(query: str, max_results: int = 3) -> str:
    """
    Backward-compatible wrapper that returns only the formatted context text.
    """
    text, _status = duckduckgo_search_context(query, max_results=max_results)
    return text
