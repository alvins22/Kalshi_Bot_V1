"""Portfolio rebalancing system with drift detection and periodic triggers"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import numpy as np
import logging

from src.data.models import Signal, Direction, Outcome, Portfolio

logger = logging.getLogger(__name__)


@dataclass
class RebalanceAction:
    strategy_type: str
    direction: str
    current_pct: float
    target_pct: float
    amount_to_trade: float
    reason: str


@dataclass
class RebalanceConfig:
    enabled: bool = True
    drift_threshold_pct: float = 0.05
    min_trade_size: int = 100
    strategy_targets: Dict[str, Dict] = field(default_factory=dict)


class PortfolioRebalancer:
    """Portfolio rebalancing with drift and periodic triggers"""

    def __init__(self, config: RebalanceConfig):
        self.config = config
        self.last_rebalance_time: Optional[datetime] = None
        self.rebalance_history: List[Dict] = []

    def check_rebalance_needed(
        self,
        portfolio: Portfolio,
        current_time: datetime = None
    ) -> Tuple[bool, List[RebalanceAction]]:
        """Check if rebalancing needed"""
        if not self.config.enabled:
            return False, []

        current_time = current_time or datetime.utcnow()
        actions = []

        # Calculate current allocations
        total_value = portfolio.total_value
        if total_value <= 0:
            return False, []

        strategy_allocations = self._calculate_strategy_allocations(portfolio)

        # Drift-based triggers
        for strategy_type, target_config in self.config.strategy_targets.items():
            current = strategy_allocations.get(strategy_type, 0.0)
            target = target_config.get('target', 0.0)
            drift = abs(current - target)

            if drift > self.config.drift_threshold_pct:
                direction = 'TRIM' if current > target else 'ADD'
                actions.append(RebalanceAction(
                    strategy_type=strategy_type,
                    direction=direction,
                    current_pct=current,
                    target_pct=target,
                    amount_to_trade=drift,
                    reason=f"Drift {drift:.1%} exceeds threshold"
                ))

        # Periodic check
        if self.last_rebalance_time:
            hours_since = (current_time - self.last_rebalance_time).total_seconds() / 3600
            if hours_since >= 24:
                if not actions:
                    actions.append(RebalanceAction(
                        strategy_type='periodic',
                        direction='REBALANCE',
                        current_pct=0,
                        target_pct=0,
                        amount_to_trade=0,
                        reason="Periodic rebalancing"
                    ))

        return len(actions) > 0, actions

    def generate_rebalance_signals(
        self,
        actions: List[RebalanceAction],
        portfolio: Portfolio,
        market_states: Dict
    ) -> List[Signal]:
        """Generate signals from rebalance actions"""
        signals = []

        for action in actions:
            if action.direction == 'TRIM':
                # Generate SELL signals for trimming
                trim_signals = self._generate_trim_signals(
                    action, portfolio, market_states
                )
                signals.extend(trim_signals)

        self.last_rebalance_time = datetime.utcnow()
        return signals

    def _calculate_strategy_allocations(self, portfolio: Portfolio) -> Dict[str, float]:
        """Calculate current allocation by strategy type"""
        allocations = {}
        total_value = portfolio.total_value

        if total_value <= 0:
            return allocations

        for position in portfolio.positions.values():
            strategy = position.market_id.split('_')[0][:3]  # Extract strategy prefix
            pct = position.total_invested / total_value
            allocations[strategy] = allocations.get(strategy, 0) + pct

        return allocations

    def _generate_trim_signals(
        self,
        action: RebalanceAction,
        portfolio: Portfolio,
        market_states: Dict
    ) -> List[Signal]:
        """Generate SELL signals for trimming"""
        signals = []
        timestamp = datetime.utcnow()

        for pos_key, position in portfolio.positions.items():
            if position.contracts <= 0:
                continue

            market_id = position.market_id
            if market_id not in market_states:
                continue

            market_state = market_states[market_id]
            trim_pct = min(1.0, action.amount_to_trade)
            contracts_to_sell = int(position.contracts * trim_pct)

            if contracts_to_sell < self.config.min_trade_size:
                continue

            price = market_state.yes_mid if position.outcome == Outcome.YES else market_state.no_mid

            signal = Signal(
                timestamp=timestamp,
                market_id=market_id,
                strategy_name='PortfolioRebalancer',
                direction=Direction.SELL,
                outcome=position.outcome,
                contracts=contracts_to_sell,
                confidence=0.9,
                reason=f"Rebalance: {action.reason}",
                estimated_price=price
            )

            signals.append(signal)
            break  # Only trim one position per action

        return signals
