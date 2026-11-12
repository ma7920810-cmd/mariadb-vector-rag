"""Polite, retrying client for the MediaWiki Action API plus HTML-to-sections cleanup.

Follows Wikimedia's API etiquette: descriptive User-Agent with contact details,
serial requests with a delay, ``maxlag`` on every request, and back-off on
HTTP 429/5xx using ``Retry-After`` when the server sends it.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from src.config import WIKI_API_URL, WIKI_CONTACT, WIKI_REQUEST_DELAY

log = logging.getLogger(__name__)

USER_AGENT = (
    f"ConstructorUniversityVectorRAG/0.2 ({WIKI_CONTACT}) "
    f"python-requests/{requests.__version__}"
)
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_API_ERRORS = {"maxlag", "ratelimited", "readonly", "internal_api_error_DBQueryError"}

# Sections that hold references or navigation rather than article knowledge.
SKIP_SECTIONS = {
    "references", "external links", "see also", "notes", "further reading",
    "bibliography", "sources", "citations", "footnotes", "works cited",
    "notes and references", "references and notes", "explanatory notes",
    "general and cited sources", "cited sources", "literature", "gallery",
}
# Elements removed before text extraction.
NOISE_SELECTORS = [
    "style", "script", "link", "meta", "table", "figure", "noscript",
    "sup.reference", "sup.noprint", "sup.Inline-Template",
    ".mw-editsection", ".reference", ".reflist", ".mw-references-wrap",
    ".navbox", ".vertical-navbox", ".infobox", ".sidebar", ".hatnote",
    ".metadata", ".ambox", ".mbox-small", ".thumb", ".gallery", ".toc",
    ".noprint", ".mw-empty-elt", ".shortdescription", ".portalbox",
    ".side-box", ".navigation-not-searchable", ".mw-cite-backlink",
]
LEAD_SECTION = "Introduction"


class WikipediaError(RuntimeError):
    """The API returned an error that retrying will not fix."""


@dataclass
class PageInfo:
    requested_title: str
    title: str | None = None
    page_id: int | None = None
    rev_id: int | None = None
    length: int = 0
    description: str | None = None
    missing: bool = False
    disambiguation: bool = False


@dataclass
class Section:
    heading: str
    text: str


@dataclass
class Article:
    title: str
    page_id: int
    rev_id: int
    url: str
    description: str | None = None
    sections: list[Section] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.sections)


def article_url(title: str) -> str:
    """Canonical article URL. Kept identical to the original ingest.py encoding
    so rows ingested before this change are matched, not duplicated."""
    return "https://en.wikipedia.org/wiki/" + requests.utils.quote(
        title.replace(" ", "_"), safe="()_,-"
    )


class WikipediaClient:
    def __init__(self, api_url=WIKI_API_URL, delay=WIKI_REQUEST_DELAY,
                 max_retries=5, timeout=30, session=None, sleep=time.sleep):
        self.api_url = api_url
        self.delay = delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT,
                                     "Accept-Encoding": "gzip"})
        self._sleep = sleep
        self._last_request = 0.0

    # -- transport -----------------------------------------------------------
    def _get(self, params: dict) -> dict:
        params = {"format": "json", "formatversion": 2, "maxlag": 5, **params}
        attempt = 0
        while True:
            wait = self.delay - (time.monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
            self._last_request = time.monotonic()
            retry_after = None
            try:
                response = self.session.get(self.api_url, params=params,
                                            timeout=self.timeout)
                if response.status_code in RETRY_STATUS:
                    retry_after = response.headers.get("Retry-After")
                    reason = f"HTTP {response.status_code}"
                else:
                    response.raise_for_status()
                    data = response.json()
                    error = data.get("error")
                    if not error:
                        return data
                    if error.get("code") not in RETRY_API_ERRORS:
                        raise WikipediaError(
                            f"{error.get('code')}: {error.get('info')}")
                    retry_after = response.headers.get("Retry-After")
                    reason = f"API error {error.get('code')}"
            except (requests.ConnectionError, requests.Timeout) as exc:
                reason = type(exc).__name__
            except ValueError as exc:  # invalid JSON (e.g. HTML error page)
                reason = f"invalid JSON: {exc}"

            attempt += 1
            if attempt > self.max_retries:
                raise WikipediaError(
                    f"Giving up after {self.max_retries} retries ({reason})")
            backoff = min(60.0, 2.0 ** attempt)
            if retry_after:
                try:
                    backoff = max(backoff, float(retry_after))
                except ValueError:
                    pass
            log.warning("Wikipedia request failed (%s); retry %d/%d in %.0fs",
                        reason, attempt, self.max_retries, backoff)
            self._sleep(backoff)

    # -- metadata ------------------------------------------------------------
    def page_info(self, titles: list[str]) -> list[PageInfo]:
        """Resolve titles (normalisation + redirects) and return page metadata.

        Uses one request per 50 titles, so checking the whole corpus for
        changes is cheap compared to downloading every article.
        """
        results = []
        for start in range(0, len(titles), 50):
            batch = titles[start:start + 50]
            data = self._get({
                "action": "query", "titles": "|".join(batch), "redirects": 1,
                "prop": "info|pageprops",
                "ppprop": "disambiguation|wikibase-shortdesc",
            })
            query = data.get("query", {})
            mapping = {}
            for item in query.get("normalized", []) + query.get("redirects", []):
                mapping[item["from"]] = item["to"]
            pages = {p["title"]: p for p in query.get("pages", [])}
            for requested in batch:
                resolved, seen = requested, set()
                while resolved in mapping and resolved not in seen:
                    seen.add(resolved)
                    resolved = mapping[resolved]
                page = pages.get(resolved)
                info = PageInfo(requested_title=requested, title=resolved)
                if page is None or page.get("missing") or page.get("invalid"):
                    info.missing = True
                else:
                    props = page.get("pageprops", {})
                    info.page_id = int(page["pageid"])
                    info.rev_id = int(page.get("lastrevid", 0)) or None
                    info.length = int(page.get("length", 0))
                    info.description = props.get("wikibase-shortdesc")
                    info.disambiguation = "disambiguation" in props
                results.append(info)
        return results

    def category_members(self, category: str, limit: int = 50) -> list[str]:
        """Article titles (namespace 0) directly inside a category."""
        if not category.startswith("Category:"):
            category = "Category:" + category
        titles, cont = [], {}
        while len(titles) < limit:
            data = self._get({
                "action": "query", "list": "categorymembers",
                "cmtitle": category, "cmnamespace": 0, "cmtype": "page",
                "cmlimit": min(500, limit - len(titles)), **cont,
            })
            titles += [m["title"] for m in data.get("query", {})
                       .get("categorymembers", [])]
            if "continue" not in data:
                break
            cont = data["continue"]
        return titles[:limit]

    # -- content -------------------------------------------------------------
    def fetch_article(self, page_id: int, description: str | None = None) -> Article:
        data = self._get({
            "action": "parse", "pageid": page_id, "prop": "text|revid",
            "disableeditsection": 1, "disabletoc": 1, "disablelimitreport": 1,
        })
        parsed = data["parse"]
        title = parsed["title"]
        return Article(
            title=title,
            page_id=int(parsed["pageid"]),
            rev_id=int(parsed["revid"]),
            url=article_url(title),
            description=description,
            sections=html_to_sections(parsed["text"]),
        )


# -- HTML cleanup --------------------------------------------------------------
def _clean_inline(text: str) -> str:
    text = re.sub(r"\[(?:\d+|[a-z]|citation needed|edit|note \d+)\]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?%)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    return text.strip()


def _replace_math(root: Tag) -> None:
    """Replace MathML/SVG math with its TeX alt text instead of garbled glyphs."""
    for node in root.select(".mwe-math-element"):
        math = node.find("math")
        tex = (math.get("alttext") if math else None) or ""
        if not tex:
            img = node.find("img")
            tex = img.get("alt", "") if img else ""
        tex = re.sub(r"^\{\\displaystyle\s*(.*)\}$", r"\1", tex.strip(), flags=re.S)
        node.replace_with(NavigableString(f" {tex.strip()} " if tex else " "))


def _block_text(tag: Tag) -> str:
    if tag.name in ("ul", "ol", "dl"):
        items = [_clean_inline(li.get_text(""))
                 for li in tag.find_all(["li", "dd", "dt"], recursive=False)]
        items = [item for item in items if item]
        if not items:
            return ""
        text = "; ".join(item.rstrip(".;") for item in items)
        return text + "."
    return _clean_inline(tag.get_text(""))


def _iter_blocks(node: Tag):
    """Yield ('heading', level, text) or ('text', None, text) in document order."""
    for child in node.children:
        if not isinstance(child, Tag):
            continue
        classes = child.get("class") or []
        if child.name in ("h2", "h3", "h4"):
            yield "heading", int(child.name[1]), _clean_inline(child.get_text(""))
        elif child.name == "div" and "mw-heading" in classes:
            heading = child.find(["h2", "h3", "h4"])
            if heading:
                yield "heading", int(heading.name[1]), _clean_inline(heading.get_text(""))
        elif child.name in ("p", "ul", "ol", "dl", "blockquote"):
            yield "text", None, _block_text(child)
        elif child.name in ("div", "section"):
            yield from _iter_blocks(child)


def html_to_sections(html: str) -> list[Section]:
    """Convert parsed article HTML into (heading, text) sections.

    Headings are kept (as "H2 > H3") so chunks carry their context; reference
    and navigation sections are dropped entirely.
    """
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".mw-parser-output") or soup
    _replace_math(root)
    for selector in NOISE_SELECTORS:
        for tag in root.select(selector):
            tag.decompose()
    for sup in root.find_all("sup"):  # remaining superscripts are real exponents
        sup.replace_with(NavigableString("^" + sup.get_text("")))

    sections: list[Section] = []
    path = {2: None, 3: None, 4: None}
    skipping = False
    current, paragraphs = LEAD_SECTION, []

    def flush():
        text = "\n\n".join(p for p in paragraphs if p)
        if text and not skipping:
            sections.append(Section(current, text))

    for kind, level, text in _iter_blocks(root):
        if kind == "heading":
            flush()
            paragraphs = []
            path[level] = text
            for deeper in range(level + 1, 5):
                path[deeper] = None
            skipping = (path[2] or "").strip().lower() in SKIP_SECTIONS
            current = " > ".join(p for p in (path[2], path[3], path[4]) if p)
        elif text:
            paragraphs.append(text)
    flush()
    return sections
