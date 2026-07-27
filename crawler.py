"""合规的公众人物公开信息聚合器。

只访问配置中明确给出的公开网页，遵守 robots.txt，并限制域名、速度和页数。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

import logging


USER_AGENT = "PublicFigureResearchBot/1.0 (+personal research; respectful crawling)"
DATE_PATTERNS = (
    re.compile(r"\b(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)\b"),
    re.compile(r"\b(20\d{2}-\d{2}-\d{2}T[\d:.+-]+Z?)\b"),
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    person: str
    aliases: tuple[str, ...]
    seed_urls: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    max_pages: int
    max_pages_per_domain: int
    follow_links: bool
    delay_seconds: float
    output_csv: Path


def load_settings(path: Path) -> Settings:
    data = json.loads(path.read_text(encoding="utf-8"))
    person = str(data["person"]).strip()
    seeds = tuple(normalize_url(url) for url in data["seed_urls"])
    if not person or not seeds:
        raise ValueError("person 和 seed_urls 不能为空")

    domains = tuple(
        sorted(
            {
                (urlparse(url).hostname or "").lower().removeprefix("www.")
                for url in seeds
            }
        )
    )
    configured_domains = data.get("allowed_domains")
    if configured_domains:
        domains = tuple(
            str(domain).lower().removeprefix("www.")
            for domain in configured_domains
        )

    return Settings(
        person=person,
        aliases=tuple(str(x).strip() for x in data.get("aliases", []) if str(x).strip()),
        seed_urls=seeds,
        allowed_domains=domains,
        max_pages=max(1, min(int(data.get("max_pages", 30)), 500)),
        max_pages_per_domain=max(
            1, min(int(data.get("max_pages_per_domain", 8)), 100)
        ),
        follow_links=bool(data.get("follow_links", True)),
        delay_seconds=max(float(data.get("delay_seconds", 1.5)), 0.5),
        output_csv=Path(data.get("output_csv", "data/public_figure.csv")),
    )


def normalize_url(url: str) -> str:
    clean, _ = urldefrag(str(url).strip())
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"不是有效的 HTTP(S) 地址：{url}")
    return clean


def domain_allowed(url: str, allowed_domains: Iterable[str]) -> bool:
    hostname = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return any(hostname == domain or hostname.endswith("." + domain) for domain in allowed_domains)


def readable_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def decode_html(content: bytes, declared_encoding: str | None, names: tuple[str, ...]) -> str:
    """选择最可能正确的网页编码，兼容未声明编码的旧中文网页。"""
    encodings: list[str] = ["utf-8", "gb18030"]
    if declared_encoding and declared_encoding.lower() not in {"iso-8859-1", "ascii"}:
        encodings.insert(0, declared_encoding)

    candidates: list[str] = []
    for encoding in dict.fromkeys(encodings):
        try:
            # 旧网页可能混入少量不符合其主编码的字节。容错解码后再根据
            # 姓名命中数、中文字符数量和替换符数量选择最佳结果。
            candidates.append(content.decode(encoding, errors="replace"))
        except LookupError:
            continue
    if not candidates:
        return content.decode("utf-8", errors="replace")

    def score(candidate: str) -> tuple[int, int, int]:
        name_hits = sum(candidate.casefold().count(name.casefold()) for name in names)
        chinese_chars = sum("\u4e00" <= char <= "\u9fff" for char in candidate)
        replacement_chars = candidate.count("\ufffd")
        return name_hits, chinese_chars, -replacement_chars

    return max(candidates, key=score)


def find_date(soup: BeautifulSoup, text: str) -> str:
    selectors = (
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ("time[datetime]", "datetime"),
    )
    for selector, attribute in selectors:
        node = soup.select_one(selector)
        if node and node.get(attribute):
            return str(node[attribute]).strip()
    for pattern in DATE_PATTERNS:
        match = pattern.search(text[:3000])
        if match:
            return match.group(1)
    return ""


def make_snippet(text: str, names: tuple[str, ...], radius: int = 180) -> str:
    lowered = text.casefold()
    positions: list[int] = []
    for name in names:
        positions.extend(match.start() for match in re.finditer(re.escape(name.casefold()), lowered))
    if not positions:
        return ""

    profile_terms = ("作者简介", "个人简介", "毕业", "研究", "出版", "著有", "学者")

    def context_score(position: int) -> tuple[int, int]:
        context = text[max(0, position - radius) : position + radius]
        score = sum(2 for term in profile_terms if term in context)
        score += sum(context.casefold().count(name.casefold()) for name in names)
        return score, position

    position = max(positions, key=context_score)
    start = max(0, position - radius)
    end = min(len(text), position + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end] + suffix


class PublicFigureCrawler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.robots: dict[str, RobotFileParser] = {}

    def robot_allows(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            parser = RobotFileParser()
            parser.set_url(origin + "/robots.txt")
            try:
                parser.read()
            except OSError:
                parser = RobotFileParser()
                parser.parse([])
            self.robots[origin] = parser
        return self.robots[origin].can_fetch(USER_AGENT, url)

    def crawl(self) -> list[dict[str, str]]:
        names = (self.settings.person, *self.settings.aliases)
        queue = deque(self.settings.seed_urls)
        seen: set[str] = set()
        pages_per_domain: dict[str, int] = {}
        results: list[dict[str, str]] = []

        while queue and len(seen) < self.settings.max_pages:
            url = queue.popleft()
            key = url.rstrip("/")
            if key in seen or not domain_allowed(url, self.settings.allowed_domains):
                continue
            domain = (urlparse(url).hostname or "").lower().removeprefix("www.")
            if pages_per_domain.get(domain, 0) >= self.settings.max_pages_per_domain:
                continue
            seen.add(key)
            pages_per_domain[domain] = pages_per_domain.get(domain, 0) + 1

            if not self.robot_allows(url):
                logger.warning("跳过 robots.txt 禁止的页面：%s", url)
                continue

            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                if "text/html" not in response.headers.get("Content-Type", ""):
                    continue
            except requests.RequestException as error:
                logger.warning("访问失败：%s：%s", url, error)
                continue

            html = decode_html(response.content, response.encoding, names)
            soup = BeautifulSoup(html, "html.parser")
            text = readable_text(soup)
            snippet = make_snippet(text, names)
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            if snippet or any(name.casefold() in title.casefold() for name in names):
                results.append(
                    {
                        "person": self.settings.person,
                        "title": title,
                        "published_date": find_date(soup, text),
                        "snippet": snippet,
                        "source_url": response.url,
                        "source_domain": urlparse(response.url).hostname or "",
                        "collected_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                logger.info("找到相关页面：%s", title or "(无标题)")
            else:
                logger.info("已检查：%s", url)

            if self.settings.follow_links:
                for link in soup.select("a[href]"):
                    try:
                        child = normalize_url(urljoin(response.url, str(link["href"])))
                    except ValueError:
                        continue
                    if domain_allowed(child, self.settings.allowed_domains):
                        queue.append(child)

            time.sleep(self.settings.delay_seconds)

        return deduplicate(results)


def deduplicate(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: dict[str, dict[str, str]] = {}
    for row in rows:
        unique.setdefault(row["source_url"].rstrip("/"), row)
    return list(unique.values())


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "person",
        "title",
        "published_date",
        "snippet",
        "source_url",
        "source_domain",
        "collected_at",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "crawler.log", encoding="utf-8"),
        ],
    )

    parser = argparse.ArgumentParser(description="采集指定公开来源中的公众人物相关页面")
    parser.add_argument("-c", "--config", default="config.json", help="JSON 配置文件路径")
    args = parser.parse_args()

    settings = load_settings(Path(args.config))
    crawler = PublicFigureCrawler(settings)
    rows = crawler.crawl()
    write_csv(settings.output_csv, rows)
    logger.info("完成：找到 %s 个相关页面，结果保存到 %s", len(rows), settings.output_csv)
    

if __name__ == "__main__":
    main()
