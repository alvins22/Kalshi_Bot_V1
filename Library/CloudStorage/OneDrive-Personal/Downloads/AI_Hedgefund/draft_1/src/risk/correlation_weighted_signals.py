"""Correlation-aware signal weighting and position concentration limits"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from src.data.models import Signal, Direction, Outcome, Portfolio, Position
from src.risk.dynamic_correlation import DynamicCorrelation

logger = logging.getLogger(__name__)


@dataclass
class ConcentrationRisk:
    """Risk metrics for position concentration"""
    total_portfolio_value: float
    position_concentrations: Dict[Outcome, float]  # outcome -> % of portfolio
    market_concentrations: Dict[str, float]  # market_id -> % of portfolio
    correlated_cluster_pct: float  # % in highly correlated positions
    max_concentration: float
    risk_level: str  # 'low', 'medium', 'high'


class CorrelationWeightedSignalFilter:
    """Filter and weight signals based on portfolio correlation"""

    def __init__(self, dcc: Optional[DynamicCorrelation] = None, config: Dict = None):
        self.dcc = dcc
        self.config = config or {}
        self.correlation_threshold = self.config.get('correlation_threshold', 0.70)
        self.max_correlated_cluster_pct = self.config.get('max_correlated_cluster_pct', 0.40)
        self.diversification_weight = self.config.get('diversification_weight', 0.5)

    def calculate_signal_weight_adjustment(
        self,
        signal: Signal,
        portfolio: Portfolio,
    ) -> float:
        """Calculate weight adjustment for signal based on portfolio correlation

        Args:
            signal: New signal to evaluate
            portfolio: Current portfolio

        Returns:
            Weight multiplier (0.0 to 1.0, where 1.0 = no adjustment)
        """
        if not self.dcc or not portfolio.positions:
            return 1.0  # No adjustment if no DCC or empty portfolio

        # Get current positions by outcome
        positions_by_outcome = self._group_positions_by_outcome(portfolio)

        # Get correlation of this signal with existing positions
        correlations = self.dcc.get_correlation_vector(signal.market_id)
        if not correlations:
            return 1.0

        # Calculate weighted correlation to portfolio
        total_position_value = sum(p.total_invested for p in portfolio.positions.values())
        if total_position_value == 0:
            return 1.0

        weighted_correlation = 0.0
        for market_id, correlation in correlations.items():
            # Find position in this market
            matching_positions = [
                p for p in portfolio.positions.values()
                if p.market_id == market_id
            ]

            if matching_positions:
                position = matching_positions[0]
                weight = position.total_invested / total_position_value
                weighted_correlation += correlation * weight

        # Reduce weight if highly correlated
        if weighted_correlation > self.correlation_threshold:
            adjustment = 1.0 - (weighted_correlation - self.correlation_threshold)
            adjustment = max(0.1, min(1.0, adjustment))  # Floor at 0.1x
            logger.info(
                f"Reducing signal weight to {adjustment:.2f}x due to "
                f"high correlation ({weighted_correlation:.2f}) with portfolio"
            )
            return adjustment

        return 1.0

    def check_position_concentration(
        self,
        new_signal: Signal,
        portfolio: Portfolio,
        estimated_cost: float,
    ) -> Tuple[bool, str]:
        """Check if adding position would exceed concentration limits

        Args:
            new_signal: Signal to evaluate
            portfolio: Current portfolio
            estimated_cost: Estimated cost of new position

        Returns:
            (is_acceptable, reason)
        """
        # Calculate portfolio value
        total_value = portfolio.cash + sum(p.total_invested for p in portfolio.positions.values())

        # Add estimated position cost
        new_value = total_value + estimated_cost

        # Check outcome concentration
        key = f"{new_signal.market_id}:{new_signal.outcome.value}"
        current_outcome_value = 0.0
        if key in portfolio.positions:
            current_outcome_value = portfolio.positions[key].total_invested

        new_outcome_value = current_outcome_value + estimated_cost
        outcome_concentration = new_outcome_value / new_value if new_value > 0 else 0.0

        max_outcome_concentration = self.config.get('max_outcome_concentration', 0.15)
        if outcome_concentration > max_outcome_concentration:
            return False, (
                f"Outcome concentration would be {outcome_concentration:.1%} > "
                f"{max_outcome_concentration:.1%}"
            )

        # Check market concentration
        market_positions = [p for p in portfolio.positions.values() if p.market_id == new_signal.market_id]
        current_market_value = sum(p.total_invested for p in market_positions)
        new_market_value = current_market_value + estimated_cost
        market_concentration = new_market_value / new_value if new_value > 0 else 0.0

        max_market_concentration = self.config.get('max_market_concentration', 0.20)
        if market_concentration > max_market_concentration:
            return False, (
                f"Market concentration would be {market_concentration:.1%} > "
                f"{max_market_concentration:.1%}"
            )

        return True, "Concentration limits acceptable"

    def get_concentration_risk(self, portfolio: Portfolio) -> ConcentrationRisk:
        """Get detailed concentration risk analysis

        Args:
            portfolio: Current portfolio

        Returns:
            ConcentrationRisk with detailed metrics
        """
        # Calculate portfolio value
        position_values = {
            key: position.total_invested
            for key, position in portfolio.positions.items()
        }

        total_value = portfolio.cash + sum(position_values.values())

        # Get concentrations by outcome
        outcome_concentrations = {}
        for key, value in position_values.items():
            outcome = key.split(':')[1]  # Extract outcome from key
            outcome_conc = value / total_value if total_value > 0 else 0.0
            outcome_concentrations[outcome] = outcome_concentrations.get(outcome, 0.0) + outcome_conc

        # Get concentrations by market
        market_concentrations = {}
        for key, value in position_values.items():
            market_id = key.split(':')[0]
            market_conc = value / total_value if total_value > 0 else 0.0
            market_concentrations[market_id] = market_concentrations.get(market_id, 0.0) + market_conc

        # Identify correlated clusters
        correlated_value = 0.0
        if self.dcc:
            correlation_matrix = self.dcc.get_correlation_matrix()
            if correlation_matrix is not None:
                # Find clusters of markets with high correlations
                # This is simplified - in production would use proper clustering
                for market_i, market_j in self._get_correlated_pairs(correlation_matrix):
                    positions_i = [p for p in portfolio.positions.values() if p.market_id == market_i]
                    positions_j = [p for p in portfolio.positions.values() if p.market_id == market_j]
                    if positions_i and positions_j:
                        correlated_value += (
                            sum(p.total_invested for p in positions_i) +
                            sum(p.total_invested for p in positions_j)
                        ) / 2

        correlated_cluster_pct = correlated_value / total_value if total_value > 0 else 0.0

        # Determine risk level
        max_concentration = max(outcome_concentrations.values()) if outcome_concentrations else 0.0
        if max_concentration > 0.30:
            risk_level = 'high'
        elif max_concentration > 0.15:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        return ConcentrationRisk(
            total_portfolio_value=total_value,
            position_concentrations={
                Outcome[k] if k in ['YES', 'NO'] else k: v
                for k, v in outcome_concentrations.items()
            },
            market_concentrations=market_concentrations,
            correlated_cluster_pct=correlated_cluster_pct,
            max_concentration=max_concentration,
            risk_level=risk_level,
        )

    def _group_positions_by_outcome(self, portfolio: Portfolio) -> Dict[Outcome, List[Position]]:
        """Group portfolio positions by outcome"""
        by_outcome = {}
        for position in portfolio.positions.values():
            if position.outcome not in by_outcome:
                by_outcome[position.outcome] = []
            by_outcome[position.outcome].append(position)
        return by_outcome

    def _get_correlated_pairs(self, correlation_matrix: np.ndarray) -> List[Tuple[str, str]]:
        """Extract pairs of highly correlated markets

        Args:
            correlation_matrix: Correlation matrix from DCC

        Returns:
            List of (market_i, market_j) tuples with high correlation
        """
        if correlation_matrix is None or correlation_matrix.size == 0:
            return []

        pairs = []
        try:
            for i in range(len(correlation_matrix)):
                for j in range(i + 1, len(correlation_matrix)):
                    corr = correlation_matrix[i, j]
                    if corr > self.correlation_threshold:
                        # Would need market_id mapping in production
                        pairs.append((f"market_{i}", f"market_{j}"))
        except (IndexError, TypeError):
            pass

        return pairs


class DiversificationRewardedSignalWeighter:
    """Weight signals to reward diversification"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.diversification_bonus = self.config.get('diversification_bonus', 1.2)  # 20% bonus

    def calculate_diversification_weight(
        self,
        signal: Signal,
        portfolio: Portfolio,
        correlation_weight: float = 1.0,
    ) -> float:
        """Calculate weight with diversification reward

        Args:
            signal: New signal
            portfolio: Current portfolio
            correlation_weight: Weight adjustment from correlation (0.1-1.0)

        Returns:
            Final weight multiplier
        """
        # Count unique markets in portfolio
        portfolio_markets = set(p.market_id for p in portfolio.positions.values())

        # Give bonus if signal is in new market
        if signal.market_id not in portfolio_markets:
            diversification_weight = self.diversification_bonus
            logger.info(
                f"Diversification bonus {diversification_weight:.1f}x: "
                f"entering new market {signal.market_id}"
            )
        else:
            diversification_weight = 1.0

        # Combine with correlation weight
        final_weight = correlation_weight * diversification_weight
        final_weight = max(0.1, min(2.0, final_weight))  # Bounds [0.1x, 2.0x]

        return final_weight
