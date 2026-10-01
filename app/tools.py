"""Council web tools: public-address-only transport and verified run scope."""
from urllib.parse import parse_qs, quote, urlsplit

from bs4 import BeautifulSoup
from langchain_core.tools import tool

from .execution import require_live_tools
from .safe_network import NetworkDenied, _parse_url, public_get

FETCH_CHAR_CAP = 18000


@tool
def web_search(query: str) -> str:
    """Search public web pages for current facts. Returns titles, snippets and URLs; read relevant pages before citing them."""
    require_live_tools()
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        return "Search rejected: use a query of 1–500 characters."
    try:
        # A fixed keyless endpoint through the same pinned transport as fetch.
        # DDGS's independent HTTP clients/alternate backends are not an escape.
        response = public_get("https://html.duckduckgo.com/html/?q=" + quote(query.strip(), safe=""))
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for result in soup.select(".result"):
            anchor = result.select_one("a.result__a")
            if anchor is None:
                continue
            href = anchor.get("href", "")
            parsed = urlsplit(href)
            if parsed.hostname in ("duckduckgo.com", "www.duckduckgo.com") or href.startswith("/l/?"):
                href = parse_qs(parsed.query).get("uddg", [""])[0]
            try:
                _parse_url(href)
            except NetworkDenied:
                continue
            snippet = result.select_one(".result__snippet")
            title = " ".join(anchor.get_text(" ", strip=True).split())[:300]
            body = " ".join(snippet.get_text(" ", strip=True).split())[:1200] if snippet else ""
            results.append(f"- {title}\n  {body}\n  URL: {href}")
            if len(results) == 6:
                break
        return "\n".join(results) or "Search returned no readable results. Try a broader query or state the evidence gap."
    except NetworkDenied:
        return "Search is unavailable or exceeded its safe request limits. Proceed only with stated evidence gaps."


@tool
def web_fetch(url: str) -> str:
    """Read a public HTTP(S) page as text. Private networks, nonstandard ports and oversized responses are denied."""
    require_live_tools()
    try:
        response = public_get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        if len(text) > FETCH_CHAR_CAP:
            text = text[:FETCH_CHAR_CAP] + " …[truncated]"
        return f"Content of {response.url}:\n{text}"
    except NetworkDenied:
        return "Fetch denied or unavailable: only bounded public HTTP(S) text pages are supported."


ANALYST_TOOLS = [web_search, web_fetch]
