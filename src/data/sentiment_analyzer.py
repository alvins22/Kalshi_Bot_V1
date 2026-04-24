"""Sentiment analysis with VADER and optional transformer enhancement"""

import logging
from src.data.news_models import SentimentScore

logger = logging.getLogger(__name__)

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    logger.warning("vaderSentiment not installed, using fallback analyzer")


class SentimentAnalyzer:
    """Fast sentiment analysis with VADER"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.use_transformer = self.config.get('use_transformer', False)
        self.use_llm = self.config.get('use_llm_enhancement', False)

        if VADER_AVAILABLE:
            self.vader = SentimentIntensityAnalyzer()
        else:
            self.vader = None

    def analyze(self, text: str) -> SentimentScore:
        """Analyze sentiment with calibrated scoring"""
        if self.vader:
            vader_scores = self.vader.polarity_scores(text)
            sentiment = vader_scores['compound']
        else:
            # Fallback: simple keyword-based sentiment
            sentiment = self._simple_sentiment(text)

        # Confidence calibration
        confidence = self._calibrate_confidence(text, sentiment)

        return SentimentScore(
            sentiment=sentiment,
            confidence=confidence,
            magnitude=abs(sentiment),
            source='vader'
        )

    def _simple_sentiment(self, text: str) -> float:
        """Simple fallback sentiment analysis"""
        positive_words = ['good', 'great', 'excellent', 'positive', 'up', 'high']
        negative_words = ['bad', 'terrible', 'poor', 'negative', 'down', 'low']

        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)

        if pos_count + neg_count == 0:
            return 0.0

        return (pos_count - neg_count) / (pos_count + neg_count)

    def _calibrate_confidence(self, text: str, sentiment: float) -> float:
        """Calibrate confidence based on signal strength"""
        word_count = len(text.split())

        if word_count < 5:
            return 0.3

        if abs(sentiment) > 0.7:
            return 0.85

        if 0.3 < abs(sentiment) <= 0.7:
            return 0.65

        return 0.4
