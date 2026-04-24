"""Data models for news event trading"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class NewsArticle:
    """News article with metadata"""
    article_id: str
    timestamp: datetime
    source: str
    headline: str
    description: str
    content: Optional[str] = None
    url: str = ""
    topics: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)


@dataclass
class SentimentScore:
    """Sentiment analysis result"""
    sentiment: float  # -1 to +1
    confidence: float  # 0 to 1
    magnitude: float  # abs(sentiment)
    source: str = "vader"


@dataclass
class ProcessedNews:
    """News article with sentiment and relevance"""
    article: NewsArticle
    sentiment: SentimentScore
    relevance: float
    timestamp: datetime


@dataclass
class CalendarEvent:
    """Scheduled economic event"""
    event_id: str
    event_type: str  # fomc, earnings, election, regulatory
    scheduled_time: datetime
    title: str
    description: str
    impact_level: str  # high, medium, low
    relevant_markets: List[str] = field(default_factory=list)
