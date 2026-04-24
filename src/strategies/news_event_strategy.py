"""News Event Trading Strategy"""

import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple

from src.strategies.base_strategy import BaseStrategy, MarketState
from src.data.models import Signal, Direction, Outcome, Fill
from src.data.news_fetcher import NewsFetcher
from src.data.sentiment_analyzer import SentimentAnalyzer
from src.data.market_news_mapper import MarketNewsMapper
from src.data.news_models import ProcessedNews, CalendarEvent

logger = logging.getLogger(__name__)


class NewsEventStrategy(BaseStrategy):
    """Generate signals from news sentiment and events"""

    def __init__(self, name: str = "NewsEventStrategy", config: Dict[str, Any] = None):
        super().__init__(name, config)

        self.news_fetcher = NewsFetcher(config.get('news', {}) if config else {})
        self.sentiment_analyzer = SentimentAnalyzer(config.get('sentiment', {}) if config else {})
        self.market_mapper = MarketNewsMapper(config.get('mapping', {}) if config else {})

        # Strategy parameters
        self.min_relevance = (config or {}).get('min_relevance', 0.6)
        self.min_sentiment_magnitude = (config or {}).get('min_sentiment_magnitude', 0.3)
        self.max_position_pct = (config or {}).get('max_position_pct', 0.15)

        # State tracking
        self.recent_news = {}
        self.calendar_events = {}
        self.sentiment_history = defaultdict(list)

    def initialize(self, config: Dict[str, Any], historical_data=None):
        """Initialize strategy"""
        self.config = config
        self.initialized = True
        logger.info(f"Initialized {self.name}")

    def generate_signals(self, market_state: MarketState) -> List[Signal]:
        """Generate signals from news sentiment"""
        signals = []

        # Check for breaking news
        breaking_signal = self._generate_breaking_news_signal(market_state)
        if breaking_signal:
            signals.append(breaking_signal)

        # Check for upcoming events
        pre_event_signal = self._generate_pre_event_signal(market_state)
        if pre_event_signal:
            signals.append(pre_event_signal)

        return signals

    def _generate_breaking_news_signal(
        self,
        market_state: MarketState
    ) -> Optional[Signal]:
        """Generate signal from breaking news"""
        recent_news = self.recent_news.get(market_state.market_id, [])

        if not recent_news:
            return None

        # Filter recent news (last 30 minutes)
        cutoff = datetime.utcnow() - timedelta(minutes=30)
        breaking = [n for n in recent_news if n.timestamp > cutoff]

        if not breaking:
            return None

        # Aggregate sentiment
        import numpy as np
        avg_sentiment = np.mean([n.sentiment.sentiment for n in breaking])
        avg_confidence = np.mean([n.sentiment.confidence for n in breaking])
        avg_relevance = np.mean([n.relevance for n in breaking])

        # Filter weak signals
        if abs(avg_sentiment) < self.min_sentiment_magnitude:
            return None
        if avg_relevance < self.min_relevance:
            return None

        # Map sentiment to outcome
        outcome = Outcome.YES if avg_sentiment > 0 else Outcome.NO
        direction = Direction.BUY

        # Calculate position size
        signal_strength = abs(avg_sentiment) * avg_confidence * avg_relevance
        position_size = int(10000 * signal_strength * self.max_position_pct)

        # Estimate price
        estimated_price = market_state.yes_mid if outcome == Outcome.YES else market_state.no_mid

        return Signal(
            timestamp=market_state.timestamp,
            market_id=market_state.market_id,
            strategy_name=self.name,
            direction=direction,
            outcome=outcome,
            contracts=position_size,
            confidence=min(avg_confidence * avg_relevance, 0.95),
            reason=f"Breaking news: {len(breaking)} articles, sentiment={avg_sentiment:.2f}",
            estimated_price=estimated_price
        )

    def _generate_pre_event_signal(
        self,
        market_state: MarketState
    ) -> Optional[Signal]:
        """Generate signal before scheduled events"""
        events = self.calendar_events.get(market_state.market_id, [])

        if not events:
            return None

        # Find events within 12-24h
        for event in events:
            time_to_event = (event.scheduled_time - datetime.utcnow()).total_seconds() / 3600

            if event.impact_level == 'high' and 12 <= time_to_event <= 24:
                # Pre-event positioning
                sentiment_trend = self._calculate_sentiment_trend(market_state.market_id)

                if abs(sentiment_trend) > 0.2:
                    outcome = Outcome.YES if sentiment_trend > 0 else Outcome.NO

                    return Signal(
                        timestamp=market_state.timestamp,
                        market_id=market_state.market_id,
                        strategy_name=self.name,
                        direction=Direction.BUY,
                        outcome=outcome,
                        contracts=int(10000 * 0.10),
                        confidence=0.65,
                        reason=f"Pre-event: {event.title} in {time_to_event:.1f}h",
                        estimated_price=market_state.yes_mid if outcome == Outcome.YES else market_state.no_mid
                    )

        return None

    def _calculate_sentiment_trend(self, market_id: str) -> float:
        """Calculate sentiment trend over time"""
        history = self.sentiment_history.get(market_id, [])

        if len(history) < 2:
            return 0.0

        recent = history[-5:]
        return sum(s[1] for s in recent) / len(recent)

    def update_positions(self, fills: List[Fill]):
        """Update positions"""
        for fill in fills:
            key = f"{fill.market_id}:{fill.outcome.value}"
            if key not in self.positions:
                self.positions[key] = {
                    'contracts': 0,
                    'entry_price': fill.filled_price,
                    'entry_time': fill.timestamp,
                    'total_invested': 0
                }

            pos = self.positions[key]
            pos['contracts'] += fill.contracts
            pos['total_invested'] += fill.total_cost

    def get_metrics(self) -> Dict[str, Any]:
        """Get strategy metrics"""
        return {
            'active_positions': len([p for p in self.positions.values() if p['contracts'] > 0]),
            'monitored_markets': len(self.recent_news),
            'recent_articles': sum(len(v) for v in self.recent_news.values()),
        }
