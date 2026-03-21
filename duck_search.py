import asyncio
from ddgs import DDGS

def get_duckduckgo_context(query: str, max_results: int = 3) -> str:
    """
    Retrieves the top results for a query from DuckDuckGo 
    and formats them into a context string for the AI.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            
        if not results:
            return "No search results found."
            
        context = "Here is some current information from the web to help answer the user:\n\n"
        for idx, res in enumerate(results, 1):
            context += f"Result {idx}:\n"
            context += f"Title: {res.get('title')}\n"
            context += f"Content: {res.get('body')}\n"
            context += f"Source: {res.get('href')}\n\n"
            
        return context.strip()
    except Exception as e:
        print(f"[ChatBuddy] DuckDuckGo Search Error: {e}")
        return "Web search is currently unavailable."
