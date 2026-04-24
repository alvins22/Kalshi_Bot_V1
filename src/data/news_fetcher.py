"""News fetcher with multi-source aggregation and caching"""

import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import hashlib
import logging

from src.data.news_models import NewsArticle, CalendarEvent

logger = logging.getLogger(__name__)


class NewsFetcher:
    """Fetch news from multiple sources with caching and deduplication"""

    def __init__(self, config: Dict):
        self.newsapi_key = config.get('newsapi_key', '')
        self.alphavantage_key = config.get('alphavantage_key', '')
        self.cache_ttl = config.get('cache_ttl', 300)
        self.cache = {}
        self.seen_articles = set()

    async def fetch_news(
        self,
        topics: List[str],
        lookback_hours: int = 24
    ) -> List[NewsArticle]:
        """Fetch news for multiple topics, cached"""
        articles = []

        # Check cache
        cache_key = f"news_{','.join(sorted(topics))}"
        if cache_key in self.cache:
            cached_time, cached_articles = self.cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_articles

        # Simulate fetching from NewsAPI
        # In production, would call actual API
        for topic in topics:
            # Mock articles for testing
            article = NewsArticle(
                article_id=self._hash_headline(f"{topic} test"),
                timestamp=datetime.utcnow(),
                source="newsapi",
                headline=f"Test news: {topic}",
                description=f"Test description for {topic}",
                topics=[topic]
            )

            if article.article_id not in self.seen_articles:
                articles.append(article)
                self.seen_articles.add(article.article_id)

        # Cache results
        self.cache[cache_key] = (time.time(), articles)

        return articles

    async def fetch_calendar_events(
        self,
        lookback_hours: int = 24,
        lookahead_hours: int = 48
    ) -> List[CalendarEvent]:
        """Fetch scheduled economic events"""
        events = []

        # Mock FOMC event
        now = datetime.utcnow()
        fomc_time = now + timedelta(hours=lookahead_hours)

        fomc_event = CalendarEvent(
            event_id="FOMC-2025-01",
            event_type="fomc",
            scheduled_time=fomc_time,
            title="Federal Open Market Committee Meeting",
            description="FOMC policy decision and press conference",
            impact_level="high",
            relevant_markets=[]
        )

        events.append(fomc_event)
        return events

    def _hash_headline(self, headline: str) -> str:
        """Hash headline for deduplication"""
        return hashlib.md5(headline.encode()).hexdigest()

    def _deduplicate(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """Remove duplicate articles"""
        unique = []
        for article in articles:
            if article.article_id not in self.seen_articles:
                unique.append(article)
                self.seen_articles.add(article.article_id)
        return unique
