"""Agent 1's tools: web search (DuckDuckGo, keyless) and web fetch."""

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from langchain_core.tools import tool

FETCH_CHAR_CAP = 18000
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


@tool
def web_search(query: str) -> str:
    """Search the web for current information. Returns top results with title, snippet and URL. Call this when the answer depends on facts not in the brief — market sizes, competitors, prices, recent events."""
    try:
        results = list(DDGS().text(query, max_results=6))
    except Exception as e:  # noqa: BLE001
        return f"Search failed: {e}. Try a different query or proceed with stated assumptions."
    if not results:
        return "No results found. Try a broader query."
    lines = []
    for r in results:
        lines.append(f"- {r.get('title', '')}\n  {r.get('body', '')}\n  URL: {r.get('href', '')}")
    return "\n".join(lines)


@tool
def web_fetch(url: str) -> str:
    """Fetch a web page and return its readable text. Call this to read a URL from the brief or a promising search result before citing it."""
    try:
        resp = httpx.get(
            url, headers={"User-Agent": UA}, timeout=15, follow_redirects=True
        )
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        return f"Fetch failed for {url}: {e}"
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype and "json" not in ctype:
        return f"Unsupported content type at {url}: {ctype}"
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    if len(text) > FETCH_CHAR_CAP:
        text = text[:FETCH_CHAR_CAP] + " …[truncated]"
    return f"Content of {url}:\n{text}"


ANALYST_TOOLS = [web_search, web_fetch]
