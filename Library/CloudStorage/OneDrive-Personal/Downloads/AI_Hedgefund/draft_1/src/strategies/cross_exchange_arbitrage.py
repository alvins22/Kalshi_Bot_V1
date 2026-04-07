"""Cross-exchange arbitrage detection between Kalshi and Polymarket"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

from src.data.models import Signal, Direction, Outcome
from src.strategies.base_strategy import BaseStrategy, MarketState

logger = logging.getLogger(__name__)


@dataclass
class ExchangePrice:
    """Price snapshot from an exchange"""
    exchange: str
    market_id: str
    timestamp: datetime
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float

    @property
    def yes_mid(self) -> float:
        return (self.yes_bid + self.yes_ask) / 2

    @property
    def no_mid(self) -> float:
        return (self.no_bid + self.no_ask) / 2

    @property
    def spread(self) -> float:
        """Total cost of matched pair"""
        return self.yes_mid + self.no_mid


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity"""
    market_id: str
    type: str  # "matched_pair" or "cross_exchange"
    buy_exchange: str
    buy_side: str  # "YES" or "NO"
    buy_price: float
    sell_exchange: str
    sell_side: str
    sell_price: float
    profit_pct: float
    profit_bps: int
    confidence: float
    reason: str


class CrossExchangeArbitrageFinder(BaseStrategy):
    """
    Find and signal arbitrage opportunities across exchanges

    Types:
    1. Matched pair (within exchange): YES + NO < 1.0
    2. Cross-exchange pricing: Exploit asymmetries between Kalshi and Polymarket
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize cross-exchange arbitrage finder

        Args:
            config: Configuration dict:
                - min_profit_bps: Minimum profit in basis points (default 100)
                - matched_pair_threshold: Min profit for matched pair (default 0.01)
                - cross_exchange_threshold: Min profit for cross-exchange (default 0.02)
                - max_execution_delay_ms: Max delay between legs (default 1000)
        """
        super().__init__("CrossExchangeArbitrage", config)

        self.min_profit_bps = self.config.get("min_profit_bps", 100)
        self.matched_pair_threshold = self.config.get("matched_pair_threshold", 0.01)
        self.cross_exchange_threshold = self.config.get("cross_exchange_threshold", 0.02)
        self.max_execution_delay_ms = self.config.get("max_execution_delay_ms", 1000)

        # Track prices from both exchanges
        self.kalshi_prices: Dict[str, ExchangePrice] = {}
        self.polymarket_prices: Dict[str, ExchangePrice] = {}
        self.detected_opportunities: List[ArbitrageOpportunity] = []

    def initialize(self, config: Dict[str, Any], historical_data=None):
        """Initialize strategy"""
        self.config.update(config)
        self.initialized = True

    def update_kalshi_price(self, market_state: MarketState):
        """Update Kalshi price snapshot"""
        price = ExchangePrice(
            exchange="kalshi",
            market_id=market_state.market_id,
            timestamp=market_state.timestamp,
            yes_bid=market_state.yes_bid,
            yes_ask=market_state.yes_ask,
            no_bid=market_state.no_bid,
            no_ask=market_state.no_ask,
        )
        self.kalshi_prices[market_state.market_id] = price

    def update_polymarket_price(self, market_id: str, timestamp: datetime, yes_bid: float, yes_ask: float, no_bid: float, no_ask: float):
        """Update Polymarket price snapshot"""
        price = ExchangePrice(
            exchange="polymarket",
            market_id=market_id,
            timestamp=timestamp,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=no_bid,
            no_ask=no_ask,
        )
        self.polymarket_prices[market_id] = price

    def generate_signals(self, market_state: MarketState) -> List[Signal]:
        """
        Generate cross-exchange arbitrage signals

        Args:
            market_state: Kalshi market state

        Returns:
            List of arbitrage signals
        """
        signals = []

        # Update Kalshi prices
        self.update_kalshi_price(market_state)

        market_id = market_state.market_id

        # Check for matching Polymarket prices
        if market_id not in self.polymarket_prices:
            return signals

        kalshi = self.kalshi_prices[market_id]
        polymarket = self.polymarket_prices[market_id]

        # Find arbitrage opportunities
        opportunities = self._find_arbitrage_opportunities(kalshi, polymarket, market_id)

        for opp in opportunities:
            self.detected_opportunities.append(opp)

            # Generate signal for arbitrage
            signal = self._create_arbitrage_signal(opp, market_state.timestamp)
            if signal:
                signals.append(signal)

        return signals

    def update_positions(self, fills):
        """Update positions after fills"""
        pass  # Stateless

    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics"""
        return {
            "total_opportunities_detected": len(self.detected_opportunities),
            "recent_opportunities": [opp.__dict__ for opp in self.detected_opportunities[-10:]],
        }

    def _find_arbitrage_opportunities(
        self, kalshi: ExchangePrice, polymarket: ExchangePrice, market_id: str
    ) -> List[ArbitrageOpportunity]:
        """
        Find arbitrage opportunities between two exchanges

        Returns:
            List of detected arbitrage opportunities
        """
        opportunities = []

        # 1. MATCHED PAIR ARBITRAGE (within single exchange)
        kalshi_opp = self._find_matched_pair(kalshi)
        if kalshi_opp:
            opportunities.append(kalshi_opp)

        polymarket_opp = self._find_matched_pair(polymarket)
        if polymarket_opp:
            opportunities.append(polymarket_opp)

        # 2. CROSS-EXCHANGE ASYMMETRIC PRICING
        # Check if YES is cheap on one exchange and NO on the other
        cross_opps = self._find_cross_exchange_arbitrage(kalshi, polymarket, market_id)
        opportunities.extend(cross_opps)

        return opportunities

    def _find_matched_pair(self, exchange_price: ExchangePrice) -> Optional[ArbitrageOpportunity]:
        """
        Find matched pair arbitrage (YES + NO < 1.0)

        Args:
            exchange_price: Price snapshot from exchange

        Returns:
            Arbitrage opportunity or None
        """
        # Use mid prices for opportunity detection, ask prices for execution
        total_cost = exchange_price.yes_mid + exchange_price.no_mid

        if total_cost >= 1.0:
            return None

        profit = 1.0 - total_cost

        if profit < self.matched_pair_threshold:
            return None

        profit_bps = int(profit * 10000)

        if profit_bps < self.min_profit_bps:
            return None

        return ArbitrageOpportunity(
            market_id=exchange_price.market_id,
            type="matched_pair",
            buy_exchange=exchange_price.exchange,
            buy_side="BOTH",
            buy_price=total_cost,
            sell_exchange=exchange_price.exchange,
            sell_side="BOTH",
            sell_price=1.0,
            profit_pct=profit,
            profit_bps=profit_bps,
            confidence=0.95,  # Very high confidence for arbitrage
            reason=f"Matched pair on {exchange_price.exchange}: "
            f"YES@{exchange_price.yes_mid:.3f} + NO@{exchange_price.no_mid:.3f} = {total_cost:.3f} < 1.0",
        )

    def _find_cross_exchange_arbitrage(
        self, kalshi: ExchangePrice, polymarket: ExchangePrice, market_id: str
    ) -> List[ArbitrageOpportunity]:
        """
        Find cross-exchange arbitrage opportunities

        Types:
        1. Buy YES cheap on one exchange, sell on other (if prices differ)
        2. Exploit NO/YES asymmetries

        Args:
            kalshi: Kalshi prices
            polymarket: Polymarket prices
            market_id: Market ID

        Returns:
            List of opportunities
        """
        opportunities = []

        # Check if YES is cheap on Kalshi, expensive on Polymarket
        yes_kalshi = kalshi.yes_mid
        yes_polymarket = polymarket.yes_mid
        yes_spread = yes_polymarket - yes_kalshi

        if yes_spread > self.cross_exchange_threshold:
            # Buy YES on Kalshi, sell on Polymarket
            opp = ArbitrageOpportunity(
                market_id=market_id,
                type="cross_exchange_yes",
                buy_exchange="kalshi",
                buy_side="YES",
                buy_price=yes_kalshi,
                sell_exchange="polymarket",
                sell_side="YES",
                sell_price=yes_polymarket,
                profit_pct=yes_spread,
                profit_bps=int(yes_spread * 10000),
                confidence=0.75,
                reason=f"Cross-exchange YES spread: Kalshi ${yes_kalshi:.3f} < Polymarket ${yes_polymarket:.3f}",
            )
            opportunities.append(opp)

        # Check if NO is cheaper on Kalshi
        no_kalshi = kalshi.no_mid
        no_polymarket = polymarket.no_mid
        no_spread = no_polymarket - no_kalshi

        if no_spread > self.cross_exchange_threshold:
            # Buy NO on Kalshi, sell on Polymarket
            opp = ArbitrageOpportunity(
                market_id=market_id,
                type="cross_exchange_no",
                buy_exchange="kalshi",
                buy_side="NO",
                buy_price=no_kalshi,
                sell_exchange="polymarket",
                sell_side="NO",
                sell_price=no_polymarket,
                profit_pct=no_spread,
                profit_bps=int(no_spread * 10000),
                confidence=0.75,
                reason=f"Cross-exchange NO spread: Kalshi ${no_kalshi:.3f} < Polymarket ${no_polymarket:.3f}",
            )
            opportunities.append(opp)

        # Check diagonal: Buy YES on Polymarket, buy NO on Kalshi
        # (useful if there's inverse mispricing)
        diagonal_cost = polymarket.yes_ask + kalshi.no_ask

        if diagonal_cost < 1.0:
            profit = 1.0 - diagonal_cost

            if profit > self.cross_exchange_threshold:
                opp = ArbitrageOpportunity(
                    market_id=market_id,
                    type="cross_exchange_diagonal",
                    buy_exchange="polymarket",
                    buy_side="YES",
                    buy_price=polymarket.yes_ask,
                    sell_exchange="kalshi",
                    sell_side="NO",
                    sell_price=1.0 - kalshi.no_ask,  # Synthetic NO sale
                    profit_pct=profit,
                    profit_bps=int(profit * 10000),
                    confidence=0.70,
                    reason=f"Diagonal arb: Polymarket YES@{polymarket.yes_ask:.3f} + Kalshi NO@{kalshi.no_ask:.3f} = {diagonal_cost:.3f}",
                )
                opportunities.append(opp)

        # Filter by minimum profit threshold
        return [opp for opp in opportunities if opp.profit_bps >= self.min_profit_bps]

    def _create_arbitrage_signal(
        self, opportunity: ArbitrageOpportunity, timestamp: datetime
    ) -> Optional[Signal]:
        """Create trading signal from arbitrage opportunity"""

        if opportunity.type == "matched_pair":
            # Buy both YES and NO
            # Return two signals (one for each leg)
            # For now, return a single signal with double contracts
            return Signal(
                timestamp=timestamp,
                market_id=opportunity.market_id,
                strategy_name=self.name,
                direction=Direction.BUY,
                outcome=Outcome.BOTH,  # Special case: both
                contracts=2000,  # Will be split into 1000 YES + 1000 NO
                confidence=opportunity.confidence,
                reason=opportunity.reason,
                estimated_price=opportunity.buy_price,
            )

        elif opportunity.type == "cross_exchange_yes":
            return Signal(
                timestamp=timestamp,
                market_id=opportunity.market_id,
                strategy_name=self.name,
                direction=Direction.BUY,
                outcome=Outcome.YES,
                contracts=1000,
                confidence=opportunity.confidence,
                reason=opportunity.reason,
                estimated_price=opportunity.buy_price,
            )

        elif opportunity.type == "cross_exchange_no":
            return Signal(
                timestamp=timestamp,
                market_id=opportunity.market_id,
                strategy_name=self.name,
                direction=Direction.BUY,
                outcome=Outcome.NO,
                contracts=1000,
                confidence=opportunity.confidence,
                reason=opportunity.reason,
                estimated_price=opportunity.buy_price,
            )

        return None

    def get_recent_opportunities(self, n: int = 10) -> List[Dict]:
        """Get recent arbitrage opportunities"""
        return [opp.__dict__ for opp in self.detected_opportunities[-n:]]

    def get_best_opportunity(self) -> Optional[Dict]:
        """Get best opportunity by profit"""
        if not self.detected_opportunities:
            return None
        best = max(self.detected_opportunities, key=lambda x: x.profit_bps)
        return best.__dict__
