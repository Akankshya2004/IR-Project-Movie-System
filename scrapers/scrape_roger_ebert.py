"""
RogerEbert.com movie review scraper (HTML crawler, no API).
Parts were written with AI support.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from scraper_utils import ScraperUtils, create_movie_document

BASE_URL = "https://www.rogerebert.com"
START_LISTING_URLS = [
    "https://www.rogerebert.com/",
    "https://www.rogerebert.com/reviews",
]
DEFAULT_OUTPUT = os.path.join(
    os.path.dirname(__file__), "..", "data", "raw", "rogerebert_reviews.json"
)
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.rogerebert.com/reviews",
}


@dataclass
class ListingEntry:
    """Metadata extracted from the listing page."""

    title: str
    url: str
    year: Optional[int] = None
    critic: Optional[str] = None
    summary: str = ""


@dataclass
class ReviewDetails:
    """Information scraped from the individual review page."""

    review_text: str = ""
    rating_value: Optional[float] = None
    rating_scale: float = 4.0
    review_date: Optional[str] = None
    critic: Optional[str] = None
    movie_year: Optional[int] = None
    movie_title: Optional[str] = None
    movie_genres: List[str] = field(default_factory=list)
    movie_directors: List[str] = field(default_factory=list)
    movie_cast: List[str] = field(default_factory=list)


class RogerEbertScraper:
    """Crawler that harvests movie reviews from RogerEbert.com."""

    def __init__(
        self,
        output_file: str = DEFAULT_OUTPUT,
        request_delay: float = 2.0,
        detail_delay: float = 1.0,
    ):
        self.output_file = output_file
        self.request_delay = request_delay
        self.detail_delay = detail_delay
        self.utils = ScraperUtils()
        self.session = requests.Session()
        self.session.headers.update(REQUEST_HEADERS)
        self.documents: List[Dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def crawl(self, limit: int = 100, start_page: int = 1):
        """Iterate listing/home pages, extract review links, and scrape full reviews."""
        
        # Load existing data to avoid duplicates and support appending
        seen_review_urls: set[str] = set()
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    existing_docs = json.load(f)
                    self.documents = existing_docs
                    for doc in existing_docs:
                        if 'url' in doc:
                            seen_review_urls.add(doc['url'])
                print(f"[INFO] Loaded {len(self.documents)} existing reviews.")
            except json.JSONDecodeError:
                print("[WARN] Existing file corrupt, starting fresh.")

        collected = 0
        listing_queue: List[str] = []

        # Add requested start page plus defaults
        if start_page > 1:
            listing_queue.append(f"https://www.rogerebert.com/reviews/page/{start_page}")
        listing_queue.extend(u for u in START_LISTING_URLS if u not in listing_queue)

        while listing_queue and collected < limit:
            listing_url = listing_queue.pop(0)
            print(f"[INFO] Crawling listing page: {listing_url}")
            listing_soup = self._get_soup(listing_url, delay=self.request_delay)
            if not listing_soup:
                continue

            entries, discovered_next = self._parse_listing(listing_soup, listing_url)
            for next_url in discovered_next:
                if next_url not in listing_queue:
                    listing_queue.append(next_url)

            if not entries:
                print(f"[WARN] No review links found on {listing_url}")
                continue

            for entry in entries:
                if collected >= limit:
                    break
                if entry.url in seen_review_urls:
                    continue

                details = self._fetch_review(entry.url)
                if not details:
                    continue

                document = self._build_document(entry, details)
                self.documents.append(document)
                seen_review_urls.add(entry.url)
                collected += 1
                
                # Save periodically
                if collected % 10 == 0:
                    self.save(verbose=False)

        print(f"[INFO] Crawl finished. New reviews collected: {collected}. Total: {len(self.documents)}")

    def save(self, verbose=True):
        """Persist scraped reviews to disk."""
        if not self.documents:
            if verbose: print("[INFO] No reviews collected; skipping save.")
            return

        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as fh:
            json.dump(self.documents, fh, indent=2, ensure_ascii=False)
        if verbose: print(f"[INFO] Saved {len(self.documents)} reviews to {self.output_file}")
        print(f"[INFO] Saved {len(self.documents)} reviews to {self.output_file}")

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _parse_listing(self, soup: BeautifulSoup, source_url: str) -> (List[ListingEntry], List[str]):
        """Extract all review links from a generic page."""
        entries: List[ListingEntry] = []
        next_listing_urls: List[str] = []
        seen_urls: set[str] = set()

        link_candidates = soup.select('a[href*="/reviews/"]')
        for link in link_candidates:
            href = link.get("href")
            if not href:
                continue
            review_url = urllib.parse.urljoin(BASE_URL, href)
            if not self._looks_like_review(review_url):
                continue
            if review_url in seen_urls:
                continue

            title = self.utils.clean_text(link.get_text()) or "Untitled Review"
            summary = self._extract_summary_near_link(link)
            year = self.utils.extract_year(title) or self.utils.extract_year(summary)

            entries.append(ListingEntry(title=title, url=review_url, year=year, critic=None, summary=summary))
            seen_urls.add(review_url)

            if len(entries) >= 50:  # don't explode from nav bars
                break

        next_listing_urls = self._extract_next_listing_urls(soup, source_url)
        return entries, next_listing_urls

    def _looks_like_review(self, url: str) -> bool:
        """Heuristic: ensure URL path starts with /reviews/ and includes a slug."""
        parsed = urllib.parse.urlparse(url)
        return parsed.path.startswith("/reviews/") and parsed.path.count("-") >= 2

    def _extract_summary_near_link(self, link: BeautifulSoup) -> str:
        """Attempt to extract teaser text near a review link."""
        parent = link.find_parent("article") or link.find_parent("div")
        if parent:
            teaser = parent.find(class_="review-stack__tease") or parent.find("p")
            if teaser:
                return self.utils.clean_text(teaser.get_text())
        return ""

    def _extract_next_listing_urls(self, soup: BeautifulSoup, current_url: str) -> List[str]:
        """Find pagination or 'more reviews' links on the current page."""
        urls = set()
        
        # Check for <link rel="next"> in head (common in modern WP sites)
        next_link_head = soup.select_one('link[rel="next"]')
        if next_link_head and next_link_head.get("href"):
            urls.add(urllib.parse.urljoin(current_url, next_link_head["href"]))

        next_link = soup.select_one('a[rel="next"]') or soup.select_one(".pagination__next a")
        if next_link and next_link.get("href"):
            urls.add(urllib.parse.urljoin(current_url, next_link["href"]))

        load_more = soup.find("a", string=lambda text: text and "More Reviews" in text)
        if load_more and load_more.get("href"):
            urls.add(urllib.parse.urljoin(current_url, load_more["href"]))

        return [u for u in urls if u.startswith(BASE_URL)]

    def _fetch_review(self, url: str) -> Optional[ReviewDetails]:
        """Fetch and parse an individual review page."""
        soup = self._get_soup(url, delay=self.detail_delay)
        if not soup:
            return None

        rating_value = self._extract_rating(soup)
        review_date = self._extract_review_date(soup)
        critic = self._extract_critic(soup)
        movie_title = self._extract_movie_title(soup)
        movie_year = self.utils.extract_year(movie_title or "") if movie_title else None
        summary = self._extract_summary(soup)
        genres = self._extract_genres(soup) or self._extract_metadata_list(soup, ["Genre", "Genres"])
        directors = self._extract_metadata_list(soup, ["Directed by", "Director"])
        cast = self._extract_credit_list(soup, ["Cast"])
        review_text = self._extract_review_body(soup)

        return ReviewDetails(
            review_text=review_text or summary,
            rating_value=rating_value,
            review_date=review_date,
            critic=critic,
            movie_year=movie_year,
            movie_title=movie_title,
            movie_genres=genres,
            movie_directors=directors,
            movie_cast=cast,
        )

    # ------------------------------------------------------------------
    # Document builder
    # ------------------------------------------------------------------
    def _build_document(self, entry: ListingEntry, details: ReviewDetails) -> Dict:
        """Merge listing + detail info into the normalized schema."""
        rating_normalized = None
        if details.rating_value is not None:
            rating_normalized = self.utils.normalize_rating(details.rating_value, details.rating_scale)

        title = details.movie_title or entry.title
        year = details.movie_year or entry.year

        doc = create_movie_document(
            title=title,
            year=year or 0,
            site="rogerebert",
            url=entry.url,
            rating=rating_normalized,
            genres=details.movie_genres,
            directors=details.movie_directors,
            cast=details.movie_cast,
            plot=entry.summary or details.review_text,
            reviews=details.review_text,
            num_reviews=None,
        )

        doc.update(
            {
                "critic": details.critic or entry.critic,
                "review_date": details.review_date,
                "rating_value": details.rating_value,
                "rating_scale": details.rating_scale,
                "summary": entry.summary,
            }
        )

        return doc

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------
    def _get_soup(self, url: str, delay: float = 0.0) -> Optional[BeautifulSoup]:
        if delay:
            time.sleep(delay)

        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None) if isinstance(exc, requests.HTTPError) else None
            if status in (403, 429):
                print(f"[WARN] Access blocked ({status}) for {url}. Please slow down or retry later.")
            else:
                print(f"[WARN] Failed to fetch {url}: {exc}")
            return None

    def _extract_rating(self, soup: BeautifulSoup) -> Optional[float]:
        meta = soup.select_one('meta[itemprop="ratingValue"]')
        if meta and meta.get("content"):
            try:
                return float(meta["content"])
            except ValueError:
                pass

        # Check for star-box img class (e.g. star25 -> 2.5)
        star_box = soup.select_one("div.star-box img.filled")
        if star_box:
            classes = star_box.get("class", [])
            for cls in classes:
                if cls.startswith("star") and cls[4:].isdigit():
                    try:
                        return float(cls[4:]) / 10.0
                    except ValueError:
                        pass

        star = soup.select_one("span.star-rating")
        if star and star.get("data-rating"):
            try:
                return float(star["data-rating"])
            except ValueError:
                return None

        return None

    def _extract_review_date(self, soup: BeautifulSoup) -> Optional[str]:
        meta = soup.select_one('meta[itemprop="datePublished"]')
        if meta and meta.get("content"):
            return meta["content"]

        meta_og = soup.select_one('meta[property="og:updated_time"]')
        if meta_og and meta_og.get("content"):
            return meta_og["content"].split("T")[0]

        date_el = soup.select_one("span.review-info__date") or soup.select_one("span.publish-date")
        return self.utils.clean_text(date_el.get_text()) if date_el else None

    def _extract_critic(self, soup: BeautifulSoup) -> Optional[str]:
        author = soup.select_one('meta[name="author"]')
        if author and author.get("content"):
            return author["content"]

        author_link = soup.select_one('a[href*="/contributors/"]')
        if author_link:
            return self.utils.clean_text(author_link.get_text())

        author_el = soup.select_one(".byline__name") or soup.select_one("a.author")
        return self.utils.clean_text(author_el.get_text()) if author_el else None

    def _extract_movie_title(self, soup: BeautifulSoup) -> Optional[str]:
        heading = soup.select_one("h1.page-title") or soup.select_one("h1")
        return self.utils.clean_text(heading.get_text()) if heading else None

    def _extract_summary(self, soup: BeautifulSoup) -> str:
        summary_el = soup.select_one(".review-info__deck") or soup.select_one(".article-info__deck")
        if summary_el:
            return self.utils.clean_text(summary_el.get_text(" ", strip=True))
        
        meta_desc = soup.select_one('meta[name="description"]') or soup.select_one('meta[property="og:description"]')
        if meta_desc and meta_desc.get("content"):
            return self.utils.clean_text(meta_desc["content"])

        return ""

    def _extract_primary_credit_column(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        container = soup.select_one("#content-lower")
        if not container:
            return None
        heading = container.select_one(".credit-col h4.page-title")
        if heading:
            return heading.find_parent("div")
        return None

    def _extract_genres(self, soup: BeautifulSoup) -> List[str]:
        column = self._extract_primary_credit_column(soup)
        if not column:
            return []
        genres: List[str] = []
        for link in column.select("a[href*='/genre/']"):
            text = self.utils.clean_text(link.get_text())
            if text and text.lower() not in {"movie reviews"}:
                if text not in genres:
                    genres.append(text)
        return genres

    def _extract_credit_list(self, soup: BeautifulSoup, labels: List[str]) -> List[str]:
        label_set = {label.lower() for label in labels}
        columns = soup.select("#content-lower .credit-col")
        values: List[str] = []
        for column in columns:
            heading = column.select_one("h4")
            if not heading:
                continue
            heading_text = self.utils.clean_text(heading.get_text()).lower()
            if heading_text not in label_set:
                continue
            links = column.select("li a")
            if links:
                for link in links:
                    text = self.utils.clean_text(link.get_text())
                    if text:
                        values.append(text)
            else:
                for item in column.select("li"):
                    text = self.utils.clean_text(item.get_text(" ", strip=True))
                    if text:
                        values.append(text)
        return values

    def _extract_metadata_list(self, soup: BeautifulSoup, labels: List[str]) -> List[str]:
        metadata_items = soup.select("div.review-info__item")
        values: List[str] = []
        label_set = {label.lower() for label in labels}

        for item in metadata_items:
            label_el = item.select_one("span.review-info__label")
            value_el = item.select_one("span.review-info__value")
            if not label_el or not value_el:
                continue
            label = self.utils.clean_text(label_el.get_text()).lower()
            if label not in label_set:
                continue
            raw_value = value_el.get_text(", ", strip=True)
            values.extend(self.utils.split_list(raw_value))

        if values:
            return values

        return self._extract_credit_list(soup, labels)

    def _extract_review_body(self, soup: BeautifulSoup) -> str:
        body = soup.select_one("div.review__body") or soup.select_one("div.article-body") or soup.select_one("div.entry-content")
        if not body:
            return ""
        paragraphs = [p.get_text(" ", strip=True) for p in body.select("p") if p.get_text(strip=True)]
        return " ".join(paragraphs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape movie reviews from RogerEbert.com (HTML crawler)."
    )
    parser.add_argument("--limit", type=int, default=100, help="Number of reviews to collect.")
    parser.add_argument("--start-page", type=int, default=1, help="Listing page index to start from.")
    parser.add_argument(
        "--sleep",
        type=float,
        default=2.0,
        help="Seconds to wait between listing page requests.",
    )
    parser.add_argument(
        "--detail-sleep",
        type=float,
        default=1.0,
        help="Seconds to wait before fetching each full review.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help="Destination JSON path for scraped reviews.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    scraper = RogerEbertScraper(
        output_file=args.output,
        request_delay=args.sleep,
        detail_delay=args.detail_sleep,
    )
    scraper.crawl(limit=args.limit, start_page=args.start_page)
    scraper.save()


if __name__ == "__main__":
    main()
