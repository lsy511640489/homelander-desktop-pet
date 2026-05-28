from __future__ import annotations

import html
import os
import re
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Callable, Sequence
from xml.etree import ElementTree as ET


DEFAULT_NEWS_FEEDS = [
    "https://rss.sina.com.cn/news/china/focus15.xml",
    "https://www.chinanews.com.cn/rss/scroll-news.xml",
]
DEFAULT_NEWS_TIMEOUT_SECONDS = 8.0
DEFAULT_NEWS_MAX_ITEMS = 12
DEFAULT_NEWS_ITEMS_PER_FEED = 8


@dataclass(slots=True)
class NewsItem:
    source: str
    title: str
    link: str
    published_at: datetime | None
    summary: str


@dataclass(slots=True)
class NewsDigestSnapshot:
    query: str | None
    items: list[NewsItem]
    generated_at: datetime
    source_count: int


def parse_news_feed_urls(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []

    urls: list[str] = []
    for token in re.split(r"[\s,;]+", raw_value.strip()):
        url = token.strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def load_news_feed_urls_from_environment() -> list[str]:
    urls = parse_news_feed_urls(os.environ.get("HOMELANDER_PET_NEWS_FEEDS"))
    return urls if urls else list(DEFAULT_NEWS_FEEDS)


class NewsDigestTracker:
    def __init__(
        self,
        feed_urls: Sequence[str],
        *,
        timeout_seconds: float = DEFAULT_NEWS_TIMEOUT_SECONDS,
        max_items_per_feed: int = DEFAULT_NEWS_ITEMS_PER_FEED,
        default_limit: int = DEFAULT_NEWS_MAX_ITEMS,
        fetcher: Callable[[str, float], str] | None = None,
    ) -> None:
        self.feed_urls = [feed_url.strip() for feed_url in feed_urls if feed_url.strip()]
        self.timeout_seconds = timeout_seconds
        self.max_items_per_feed = max_items_per_feed
        self.default_limit = default_limit
        self._fetcher = fetcher or self._fetch_url

    @classmethod
    def from_environment(cls) -> "NewsDigestTracker":
        feed_urls = load_news_feed_urls_from_environment()
        timeout_seconds = _read_float_env("HOMELANDER_PET_NEWS_TIMEOUT_SECONDS", DEFAULT_NEWS_TIMEOUT_SECONDS)
        max_items_per_feed = _read_int_env("HOMELANDER_PET_NEWS_ITEMS_PER_FEED", DEFAULT_NEWS_ITEMS_PER_FEED)
        default_limit = _read_int_env("HOMELANDER_PET_NEWS_MAX_ITEMS", DEFAULT_NEWS_MAX_ITEMS)
        return cls(
            feed_urls,
            timeout_seconds=timeout_seconds,
            max_items_per_feed=max_items_per_feed,
            default_limit=default_limit,
        )

    def daily_digest(self, *, query: str | None = None, limit: int | None = None) -> NewsDigestSnapshot:
        items: list[NewsItem] = []
        for feed_url in self.feed_urls:
            try:
                xml_text = self._fetcher(feed_url, self.timeout_seconds)
            except Exception:  # noqa: BLE001
                continue
            items.extend(_parse_feed_items(xml_text, fallback_source=feed_url, max_items=self.max_items_per_feed))

        if not items:
            raise RuntimeError("no news items could be fetched")

        deduped_items = _dedupe_items(items)
        normalized_query = query.strip() if query else None
        if normalized_query:
            deduped_items = [item for item in deduped_items if _matches_query(item, normalized_query)]

        deduped_items.sort(key=_sort_key, reverse=True)

        effective_limit = limit if limit and limit > 0 else self.default_limit
        if effective_limit > 0:
            deduped_items = deduped_items[:effective_limit]

        return NewsDigestSnapshot(
            query=normalized_query,
            items=deduped_items,
            generated_at=datetime.now(tz=UTC),
            source_count=len(self.feed_urls),
        )

    def _fetch_url(self, url: str, timeout_seconds: float) -> str:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "application/rss+xml,application/xml,text/xml,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")


def _parse_feed_items(xml_text: str, *, fallback_source: str, max_items: int) -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    container = _find_child(root, "channel") or root
    source_title = _first_text(container, "title") or fallback_source

    items: list[NewsItem] = []
    for entry in _iter_named_children(container, {"item", "entry"}):
        title = _first_text(entry, "title")
        if not title:
            continue
        link = _first_link(entry) or ""
        summary = _first_text(entry, "description") or _first_text(entry, "summary") or _first_text(entry, "content")
        published_at = _parse_entry_datetime(entry)
        items.append(
            NewsItem(
                source=source_title,
                title=_clean_text(title),
                link=link.strip(),
                published_at=published_at,
                summary=_clean_text(summary),
            )
        )
        if max_items > 0 and len(items) >= max_items:
            break

    return items


def _iter_named_children(element: ET.Element, names: set[str]) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) in names]


def _find_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in list(element):
        if _local_name(child.tag) == name:
            return child
    return None


def _first_text(element: ET.Element, name: str) -> str:
    child = _find_child(element, name)
    return (child.text or "").strip() if child is not None and child.text else ""


def _first_link(element: ET.Element) -> str:
    for child in list(element):
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return href.strip()
        if child.text:
            return child.text.strip()
    return ""


def _parse_entry_datetime(element: ET.Element) -> datetime | None:
    for name in ("pubDate", "published", "updated", "modified", "date"):
        raw_value = _first_text(element, name)
        if not raw_value:
            continue
        parsed = _parse_datetime(raw_value)
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(raw_value: str) -> datetime | None:
    raw_value = raw_value.strip()
    if not raw_value:
        return None

    try:
        parsed = parsedate_to_datetime(raw_value)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    normalized = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[tuple[str, str]] = set()
    deduped: list[NewsItem] = []
    for item in items:
        key = (item.title.lower(), item.link.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _matches_query(item: NewsItem, query: str) -> bool:
    haystack = " ".join([item.source, item.title, item.summary, item.link]).lower()
    needle = query.lower().strip()
    return bool(needle) and needle in haystack


def _sort_key(item: NewsItem) -> tuple[bool, datetime]:
    return (item.published_at is None, item.published_at or datetime.min.replace(tzinfo=UTC))


def _clean_text(raw_value: str) -> str:
    text = html.unescape(raw_value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_float_env(name: str, default_value: float) -> float:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default_value
    try:
        return float(raw_value)
    except ValueError:
        return default_value


def _read_int_env(name: str, default_value: int) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default_value
    try:
        return int(raw_value)
    except ValueError:
        return default_value