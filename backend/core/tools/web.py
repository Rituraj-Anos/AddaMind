"""Web search and page reading via Tavily (https://docs.tavily.com), with a direct-fetch fallback.

web_search needs TAVILY_API_KEY (the model gets a clear error without it). read_url uses Tavily
Extract when the key is set and falls back to fetching the page itself.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import Annotated, Literal
from urllib.parse import urlparse

import requests

from ..config import env_str
from .registry import tool

TAVILY = "https://api.tavily.com"
MAX_PAGE_CHARS = 8000  # what the model sees from one page; keeps Groq's 8k-token budget usable


def _tavily(path: str, body: dict, timeout: float = 25) -> dict:
    key = env_str("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    r = requests.post(f"{TAVILY}{path}", json=body, headers={"Authorization": f"Bearer {key}"},
                      timeout=(5, timeout))
    if r.status_code == 401:
        raise RuntimeError("Tavily rejected the API key")
    if r.status_code == 429:
        raise RuntimeError("Tavily rate limit reached; wait a minute")
    if not r.ok:
        raise RuntimeError(f"Tavily error {r.status_code}: {r.text[:200]}")
    return r.json()


@tool
def web_search(
    query: Annotated[str, "What to search for. Write it like a search engine query, not a question to a person."],
    max_results: Annotated[int, "How many results, 1-8"] = 5,
    topic: Annotated[Literal["general", "news", "finance"], "Use 'news' for recent events"] = "general",
) -> dict:
    """Search the web for current information. Use for facts you don't know, recent events, prices,
    or anything that may have changed. Returns titles, URLs and relevant snippets; cite the URLs."""
    data = _tavily("/search", {
        "query": query[:400],
        "max_results": max(1, min(int(max_results), 8)),
        "topic": topic,
        "search_depth": "basic",
        "include_answer": False,
    })
    results = [{"title": r.get("title", ""), "url": r.get("url", ""),
                "snippet": (r.get("content") or "")[:700],
                **({"published": r["published_date"]} if r.get("published_date") else {})}
               for r in data.get("results", [])]
    return {"query": query, "results": results, "count": len(results)}


# ---------------------------------------------------------------- read_url
class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form", "iframe"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        t = "".join(self.parts)
        t = re.sub(r"[ \t\r\f\v]+", " ", t)
        return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def _check_public_url(url: str) -> None:
    """Block non-http schemes and private/internal addresses (SSRF guard for the direct fetch)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("only http(s) URLs are allowed")
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror:
        raise ValueError(f"could not resolve host '{p.hostname}'")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("refusing to fetch a private or local address")


def _direct_fetch(url: str) -> tuple[str, str]:
    _check_public_url(url)
    r = requests.get(url, timeout=(5, 15), allow_redirects=True, stream=True,
                     headers={"User-Agent": "Mozilla/5.0 (compatible; hackathon-agent/1.0)"})
    _check_public_url(r.url)  # the final URL after redirects too
    r.raise_for_status()
    raw = r.raw.read(2_000_000, decode_content=True)  # cap at 2 MB
    ctype = r.headers.get("content-type", "")
    text = raw.decode(r.encoding or "utf-8", errors="replace")
    if "html" not in ctype and not text.lstrip().startswith("<"):
        return "", text
    ex = _TextExtractor()
    ex.feed(text)
    return ex.title.strip(), ex.text()


@tool
def read_url(url: Annotated[str, "Full http(s) URL of the page to read"]) -> dict:
    """Read the main text of a web page. Use after web_search to get details from a specific result,
    or when the user gives a link."""
    url = url.strip()
    if not urlparse(url).scheme:
        url = "https://" + url
    title, text, via = "", "", ""
    if env_str("TAVILY_API_KEY"):
        try:
            data = _tavily("/extract", {"urls": [url], "extract_depth": "basic", "format": "markdown"}, 30)
            res = data.get("results") or []
            if res:
                text, via = res[0].get("raw_content") or "", "tavily"
                title = res[0].get("title") or ""
        except RuntimeError:
            pass  # fall back to fetching it ourselves
    if not text:
        title, text = _direct_fetch(url)
        via = "direct"
    if not text.strip():
        raise ValueError("the page had no readable text (it may need JavaScript or block bots)")
    truncated = len(text) > MAX_PAGE_CHARS
    return {"url": url, "title": title, "text": text[:MAX_PAGE_CHARS], "truncated": truncated,
            "chars": len(text), "via": via}
