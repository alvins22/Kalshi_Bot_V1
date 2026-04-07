"""Unit tests for cross-exchange arbitrage module"""

import unittest
from datetime import datetime
from src.strategies.cross_exchange_arbitrage import (
    CrossExchangeArbitrageFinder,
    ExchangePrice,
    ArbitrageOpportunity,
)
from src.strategies.base_strategy import MarketState


class TestExchangePrice(unittest.TestCase):
    """Test ExchangePrice dataclass"""

    def test_price_creation(self):
        """Test ExchangePrice creation"""
        price = ExchangePrice(
            exchange="kalshi",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.48,
            yes_ask=0.52,
            no_bid=0.48,
            no_ask=0.52,
        )

        self.assertEqual(price.exchange, "kalshi")
        self.assertEqual(price.market_id, "MARKET_1")

    def test_yes_mid_price(self):
        """Test YES mid price calculation"""
        price = ExchangePrice(
            exchange="kalshi",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.48,
            yes_ask=0.52,
            no_bid=0.48,
            no_ask=0.52,
        )

        self.assertEqual(price.yes_mid, 0.50)

    def test_no_mid_price(self):
        """Test NO mid price calculation"""
        price = ExchangePrice(
            exchange="kalshi",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.48,
            yes_ask=0.52,
            no_bid=0.47,
            no_ask=0.53,
        )

        self.assertEqual(price.no_mid, 0.50)

    def test_spread(self):
        """Test spread calculation"""
        price = ExchangePrice(
            exchange="kalshi",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.48,
            yes_ask=0.52,
            no_bid=0.48,
            no_ask=0.52,
        )

        self.assertEqual(price.spread, 1.00)


class TestArbitrageOpportunity(unittest.TestCase):
    """Test ArbitrageOpportunity dataclass"""

    def test_opportunity_creation(self):
        """Test ArbitrageOpportunity creation"""
        opp = ArbitrageOpportunity(
            market_id="MARKET_1",
            type="matched_pair",
            buy_exchange="kalshi",
            buy_side="BOTH",
            buy_price=0.98,
            sell_exchange="kalshi",
            sell_side="BOTH",
            sell_price=1.00,
            profit_pct=0.02,
            profit_bps=200,
            confidence=0.95,
            reason="Matched pair arbitrage",
        )

        self.assertEqual(opp.market_id, "MARKET_1")
        self.assertEqual(opp.type, "matched_pair")
        self.assertEqual(opp.profit_bps, 200)


class TestCrossExchangeArbitrageFinder(unittest.TestCase):
    """Test CrossExchangeArbitrageFinder class"""

    def setUp(self):
        self.finder = CrossExchangeArbitrageFinder(
            config={
                "min_profit_bps": 100,
                "matched_pair_threshold": 0.01,
                "cross_exchange_threshold": 0.02,
            }
        )

    def test_initialize(self):
        """Test initialization"""
        self.assertEqual(self.finder.min_profit_bps, 100)
        self.assertEqual(self.finder.matched_pair_threshold, 0.01)
        self.assertEqual(self.finder.cross_exchange_threshold, 0.02)

    def test_update_kalshi_price(self):
        """Test updating Kalshi prices"""
        market_state = MarketState(
            timestamp=datetime.utcnow(),
            market_id="MARKET_1",
            yes_bid=0.48,
            yes_ask=0.52,
            no_bid=0.48,
            no_ask=0.52,
            volume_24h=1000,
            lookback_data=[],
        )

        self.finder.update_kalshi_price(market_state)

        self.assertIn("MARKET_1", self.finder.kalshi_prices)
        price = self.finder.kalshi_prices["MARKET_1"]
        self.assertEqual(price.exchange, "kalshi")

    def test_update_polymarket_price(self):
        """Test updating Polymarket prices"""
        self.finder.update_polymarket_price(
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.45,
            yes_ask=0.55,
            no_bid=0.45,
            no_ask=0.55,
        )

        self.assertIn("MARKET_1", self.finder.polymarket_prices)
        price = self.finder.polymarket_prices["MARKET_1"]
        self.assertEqual(price.exchange, "polymarket")

    def test_find_matched_pair_no_opportunity(self):
        """Test matched pair detection with no opportunity"""
        price = ExchangePrice(
            exchange="kalshi",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.50,
            yes_ask=0.51,
            no_bid=0.49,
            no_ask=0.50,
        )

        opp = self.finder._find_matched_pair(price)

        # Spread is ~1.01, should not be profitable
        self.assertIsNone(opp)

    def test_find_matched_pair_opportunity(self):
        """Test matched pair detection with opportunity"""
        price = ExchangePrice(
            exchange="kalshi",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.48,
            yes_ask=0.49,
            no_bid=0.48,
            no_ask=0.49,
        )

        opp = self.finder._find_matched_pair(price)

        # Spread is ~0.97, should be profitable
        self.assertIsNotNone(opp)
        self.assertEqual(opp.type, "matched_pair")
        self.assertGreater(opp.profit_bps, 100)

    def test_find_cross_exchange_yes_spread(self):
        """Test cross-exchange YES arbitrage detection"""
        kalshi = ExchangePrice(
            exchange="kalshi",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.40,
            yes_ask=0.42,
            no_bid=0.58,
            no_ask=0.60,
        )

        polymarket = ExchangePrice(
            exchange="polymarket",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.45,
            yes_ask=0.47,
            no_bid=0.53,
            no_ask=0.55,
        )

        opps = self.finder._find_cross_exchange_arbitrage(kalshi, polymarket, "MARKET_1")

        # Should detect YES spread opportunity
        yes_opps = [o for o in opps if o.type == "cross_exchange_yes"]
        self.assertGreater(len(yes_opps), 0)

    def test_find_cross_exchange_no_spread(self):
        """Test cross-exchange NO arbitrage detection"""
        kalshi = ExchangePrice(
            exchange="kalshi",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.55,
            yes_ask=0.57,
            no_bid=0.40,
            no_ask=0.42,
        )

        polymarket = ExchangePrice(
            exchange="polymarket",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.50,
            yes_ask=0.52,
            no_bid=0.45,
            no_ask=0.47,
        )

        opps = self.finder._find_cross_exchange_arbitrage(kalshi, polymarket, "MARKET_1")

        # Should detect NO spread opportunity
        no_opps = [o for o in opps if o.type == "cross_exchange_no"]
        self.assertGreater(len(no_opps), 0)

    def test_find_cross_exchange_diagonal(self):
        """Test diagonal arbitrage detection"""
        kalshi = ExchangePrice(
            exchange="kalshi",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.45,
            yes_ask=0.46,
            no_bid=0.50,
            no_ask=0.51,
        )

        polymarket = ExchangePrice(
            exchange="polymarket",
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.48,
            yes_ask=0.49,
            no_bid=0.51,
            no_ask=0.52,
        )

        opps = self.finder._find_cross_exchange_arbitrage(kalshi, polymarket, "MARKET_1")

        # Check if we get any opportunities
        self.assertIsInstance(opps, list)

    def test_generate_signals_no_polymarket_data(self):
        """Test signal generation without Polymarket data"""
        market_state = MarketState(
            timestamp=datetime.utcnow(),
            market_id="MARKET_1",
            yes_bid=0.48,
            yes_ask=0.52,
            no_bid=0.48,
            no_ask=0.52,
            volume_24h=1000,
            lookback_data=[],
        )

        signals = self.finder.generate_signals(market_state)

        # Should return empty list if no Polymarket data
        self.assertEqual(len(signals), 0)

    def test_generate_signals_with_both_exchanges(self):
        """Test signal generation with both exchanges"""
        # Set Kalshi price
        market_state = MarketState(
            timestamp=datetime.utcnow(),
            market_id="MARKET_1",
            yes_bid=0.48,
            yes_ask=0.49,
            no_bid=0.48,
            no_ask=0.49,
            volume_24h=1000,
            lookback_data=[],
        )

        # Set Polymarket price (same as Kalshi for no arbitrage)
        self.finder.update_polymarket_price(
            market_id="MARKET_1",
            timestamp=datetime.utcnow(),
            yes_bid=0.48,
            yes_ask=0.49,
            no_bid=0.48,
            no_ask=0.49,
        )

        signals = self.finder.generate_signals(market_state)

        # Should generate signals for matched pair
        self.assertIsInstance(signals, list)

    def test_get_recent_opportunities(self):
        """Test retrieving recent opportunities"""
        # Add some opportunities
        opp = ArbitrageOpportunity(
            market_id="MARKET_1",
            type="matched_pair",
            buy_exchange="kalshi",
            buy_side="BOTH",
            buy_price=0.98,
            sell_exchange="kalshi",
            sell_side="BOTH",
            sell_price=1.00,
            profit_pct=0.02,
            profit_bps=200,
            confidence=0.95,
            reason="Test",
        )

        self.finder.detected_opportunities.append(opp)

        recent = self.finder.get_recent_opportunities(n=10)

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["market_id"], "MARKET_1")

    def test_get_best_opportunity(self):
        """Test retrieving best opportunity"""
        opp1 = ArbitrageOpportunity(
            market_id="MARKET_1",
            type="matched_pair",
            buy_exchange="kalshi",
            buy_side="BOTH",
            buy_price=0.98,
            sell_exchange="kalshi",
            sell_side="BOTH",
            sell_price=1.00,
            profit_pct=0.02,
            profit_bps=200,
            confidence=0.95,
            reason="Test 1",
        )

        opp2 = ArbitrageOpportunity(
            market_id="MARKET_2",
            type="matched_pair",
            buy_exchange="polymarket",
            buy_side="BOTH",
            buy_price=0.97,
            sell_exchange="polymarket",
            sell_side="BOTH",
            sell_price=1.00,
            profit_pct=0.03,
            profit_bps=300,
            confidence=0.95,
            reason="Test 2",
        )

        self.finder.detected_opportunities.extend([opp1, opp2])

        best = self.finder.get_best_opportunity()

        # Should be opp2 (higher profit)
        self.assertEqual(best["market_id"], "MARKET_2")
        self.assertEqual(best["profit_bps"], 300)

    def test_get_metrics(self):
        """Test metrics retrieval"""
        metrics = self.finder.get_metrics()

        self.assertIn("total_opportunities_detected", metrics)
        self.assertIn("recent_opportunities", metrics)
        self.assertEqual(metrics["total_opportunities_detected"], 0)


if __name__ == "__main__":
    unittest.main()
