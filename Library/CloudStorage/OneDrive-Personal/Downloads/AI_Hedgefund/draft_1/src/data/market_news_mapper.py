"""Map news articles to relevant markets"""

from dataclasses import dataclass
from typing import List, Tuple, Dict
import logging

from src.data.news_models import NewsArticle

logger = logging.getLogger(__name__)


@dataclass
class MarketKeywordConfig:
    market_id: str
    market_title: str
    keywords: List[str]
    entities: List[str]
    exclude_keywords: List[str]
    sentiment_direction: str  # positive_yes, positive_no, neutral


class MarketNewsMapper:
    """Map news to markets via keyword matching"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.market_configs = self._load_market_configs()

    def map_news_to_markets(
        self,
        article: NewsArticle
    ) -> List[Tuple[str, float]]:
        """Map article to markets with relevance scores"""
        matches = []

        for market_id, config in self.market_configs.items():
            relevance = self._calculate_relevance(article, config)

            if relevance > 0.5:
                matches.append((market_id, relevance))

        return sorted(matches, key=lambda x: x[1], reverse=True)

    def _calculate_relevance(
        self,
        article: NewsArticle,
        config: MarketKeywordConfig
    ) -> float:
        """Calculate relevance score 0-1"""
        text = f"{article.headline} {article.description}".lower()

        # Keyword matching
        keyword_score = 0.0
        for keyword in config.keywords:
            if keyword.lower() in text:
                keyword_score += 0.3

        # Entity matching
        entity_score = 0.0
        for entity in config.entities:
            if entity.lower() in text:
                entity_score += 0.5

        # Exclude keywords
        for exclude in config.exclude_keywords:
            if exclude.lower() in text:
                return 0.0

        # Combine scores
        relevance = (
            0.4 * min(keyword_score, 1.0) +
            0.6 * min(entity_score, 1.0)
        )

        return min(relevance, 1.0)

    def _load_market_configs(self) -> Dict[str, MarketKeywordConfig]:
        """Load market keyword configurations"""
        return {
            "UNEMP-24DEC": MarketKeywordConfig(
                market_id="UNEMP-24DEC",
                market_title="Unemployment above 4.5%",
                keywords=["unemployment", "jobless", "labor", "jobs", "payroll"],
                entities=["Bureau of Labor Statistics", "BLS"],
                exclude_keywords=["crypto", "stocks"],
                sentiment_direction="positive_yes"
            ),
            "FED-RATE-JAN25": MarketKeywordConfig(
                market_id="FED-RATE-JAN25",
                market_title="Federal Reserve raises rates",
                keywords=["fed rate", "federal reserve", "fomc", "interest rate"],
                entities=["Jerome Powell", "Federal Reserve", "FOMC"],
                exclude_keywords=[],
                sentiment_direction="neutral"
            ),
        }
