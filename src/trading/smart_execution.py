"""Smart order execution with splitting, VWAP, and slippage tracking"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import math

from src.data.models import Signal, Direction, Outcome, MarketState

logger = logging.getLogger(__name__)


@dataclass
class ExecutionSlice:
    """A slice of an order to execute"""
    slice_id: int
    contracts: int
    target_time: datetime  # When this slice should be executed
    min_price: Optional[float] = None
    max_price: Optional[float] = None


@dataclass
class ExecutionPlan:
    """Plan for executing an order with multiple slices"""
    signal_id: str
    market_id: str
    total_contracts: int
    slices: List[ExecutionSlice]
    strategy: str  # 'vwap', 'twap', 'uniform', 'adaptive'
    duration_seconds: int  # Total execution duration
    volume_target_pct: float  # Target % of market volume


class OrderSplitter:
    """Splits large orders into smaller slices to minimize market impact"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.max_slice_size = self.config.get('max_slice_size', 500)
        self.min_slice_size = self.config.get('min_slice_size', 50)
        self.target_volume_pct = self.config.get('target_volume_pct', 0.10)  # Max 10% of 24h volume

    def should_split_order(self, contracts: int, market_volume_24h: int) -> bool:
        """Determine if order should be split

        Args:
            contracts: Number of contracts to trade
            market_volume_24h: 24-hour market volume

        Returns:
            True if order should be split
        """
        # Don't split small orders
        if contracts < self.max_slice_size * 1.5:
            return False

        # Don't split if order would be small % of volume
        order_pct = contracts / market_volume_24h if market_volume_24h > 0 else 1.0
        if order_pct < 0.05:  # Less than 5% of volume - acceptable
            return False

        return True

    def split_uniform(
        self,
        contracts: int,
        num_slices: int,
    ) -> List[int]:
        """Split order into uniform-sized slices

        Args:
            contracts: Total contracts
            num_slices: Number of slices

        Returns:
            List of contract counts per slice
        """
        base_size = contracts // num_slices
        remainder = contracts % num_slices

        slices = [base_size] * num_slices
        # Distribute remainder
        for i in range(remainder):
            slices[i] += 1

        return slices

    def split_vwap(
        self,
        contracts: int,
        volume_profile: List[Tuple[datetime, int]],
    ) -> Dict[datetime, int]:
        """Split order proportional to expected volume profile (VWAP)

        Args:
            contracts: Total contracts
            volume_profile: List of (time_bucket, expected_volume) tuples

        Returns:
            Dict mapping time_bucket to contracts to trade
        """
        total_expected_volume = sum(v for _, v in volume_profile)
        if total_expected_volume == 0:
            return {t: contracts // len(volume_profile) for t, _ in volume_profile}

        result = {}
        for time_bucket, expected_volume in volume_profile:
            pct = expected_volume / total_expected_volume
            contracts_for_bucket = max(int(contracts * pct), self.min_slice_size)
            result[time_bucket] = contracts_for_bucket

        return result

    def create_execution_plan(
        self,
        signal: Signal,
        market_state: MarketState,
        strategy: str = 'vwap',
        duration_minutes: int = 30,
    ) -> ExecutionPlan:
        """Create execution plan for a signal

        Args:
            signal: Trading signal
            market_state: Current market state
            strategy: Execution strategy ('vwap', 'twap', 'uniform')
            duration_minutes: How long to spread execution

        Returns:
            ExecutionPlan with slices
        """
        # Determine if order should be split
        should_split = self.should_split_order(signal.contracts, market_state.volume_24h or 1000)

        if not should_split:
            # Execute immediately
            plan = ExecutionPlan(
                signal_id=signal.signal_id or 'unknown',
                market_id=signal.market_id,
                total_contracts=signal.contracts,
                slices=[
                    ExecutionSlice(
                        slice_id=0,
                        contracts=signal.contracts,
                        target_time=datetime.utcnow(),
                    )
                ],
                strategy='immediate',
                duration_seconds=0,
                volume_target_pct=0.0,
            )
            logger.debug(f"No split needed for {signal.contracts} contracts")
            return plan

        # Determine number of slices
        num_slices = max(2, signal.contracts // self.max_slice_size)
        num_slices = min(num_slices, duration_minutes)  # Max slices = duration in minutes

        logger.info(f"Splitting order {signal.contracts} contracts into {num_slices} slices")

        # Create slices based on strategy
        slice_sizes = self.split_uniform(signal.contracts, num_slices)

        slices = []
        now = datetime.utcnow()
        time_step = duration_minutes * 60 / num_slices  # Seconds between slices

        for i, size in enumerate(slice_sizes):
            target_time = now + timedelta(seconds=i * time_step)

            # Add limit orders at mid + spread for buys, mid - spread for sells
            if signal.direction == Direction.BUY:
                max_price = signal.estimated_price + 0.02 if signal.estimated_price else None
            else:
                min_price = signal.estimated_price - 0.02 if signal.estimated_price else None

            slices.append(
                ExecutionSlice(
                    slice_id=i,
                    contracts=size,
                    target_time=target_time,
                    min_price=min_price if signal.direction == Direction.SELL else None,
                    max_price=max_price if signal.direction == Direction.BUY else None,
                )
            )

        plan = ExecutionPlan(
            signal_id=signal.signal_id or 'unknown',
            market_id=signal.market_id,
            total_contracts=signal.contracts,
            slices=slices,
            strategy=strategy,
            duration_seconds=duration_minutes * 60,
            volume_target_pct=self.target_volume_pct,
        )

        return plan


class SlippageTracker:
    """Track execution slippage against estimated prices"""

    def __init__(self):
        self.slippages: Dict[str, List[float]] = {}  # signal_id -> [slippages]
        self.execution_prices: Dict[str, List[float]] = {}  # signal_id -> [prices]
        self.estimated_prices: Dict[str, float] = {}  # signal_id -> estimated_price

    def record_execution(
        self,
        signal_id: str,
        estimated_price: float,
        executed_price: float,
    ):
        """Record execution and calculate slippage

        Args:
            signal_id: Signal ID
            estimated_price: Estimated/target price
            executed_price: Actual execution price
        """
        if signal_id not in self.slippages:
            self.slippages[signal_id] = []
            self.execution_prices[signal_id] = []

        slippage_bps = (executed_price - estimated_price) / estimated_price * 10000
        self.slippages[signal_id].append(slippage_bps)
        self.execution_prices[signal_id].append(executed_price)
        self.estimated_prices[signal_id] = estimated_price

        logger.debug(
            f"Recorded execution for {signal_id[:8]}: "
            f"estimated=${estimated_price:.4f}, actual=${executed_price:.4f}, "
            f"slippage={slippage_bps:+.1f}bps"
        )

    def get_average_slippage(self, signal_id: str) -> Optional[float]:
        """Get average slippage for a signal

        Args:
            signal_id: Signal ID

        Returns:
            Average slippage in basis points, or None
        """
        slippages = self.slippages.get(signal_id, [])
        if not slippages:
            return None
        return sum(slippages) / len(slippages)

    def get_max_slippage(self, signal_id: str) -> Optional[float]:
        """Get worst slippage for a signal"""
        slippages = self.slippages.get(signal_id, [])
        if not slippages:
            return None
        return max(slippages)

    def get_slippage_statistics(self) -> Dict[str, Dict]:
        """Get slippage statistics across all signals"""
        stats = {}
        for signal_id, slippages in self.slippages.items():
            if slippages:
                stats[signal_id] = {
                    'avg_slippage_bps': sum(slippages) / len(slippages),
                    'max_slippage_bps': max(slippages),
                    'min_slippage_bps': min(slippages),
                    'num_executions': len(slippages),
                }
        return stats


class AdaptiveExecutor:
    """Adapts execution strategy based on market conditions"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.volume_threshold = self.config.get('volume_threshold', 100)  # Min volume for order
        self.spread_threshold_bps = self.config.get('spread_threshold_bps', 50)  # Max spread to trade

    def should_execute_now(
        self,
        market_state: MarketState,
        slice: ExecutionSlice,
    ) -> bool:
        """Determine if slice should execute now

        Args:
            market_state: Current market state
            slice: Order slice

        Returns:
            True if should execute now
        """
        # Check if it's time
        if datetime.utcnow() < slice.target_time:
            return False

        # Check market conditions
        if market_state.volume_24h and market_state.volume_24h < self.volume_threshold:
            logger.warning(f"Insufficient volume {market_state.volume_24h} < {self.volume_threshold}")
            return False

        # Check spread
        spread_bps = ((market_state.yes_ask - market_state.yes_bid) / market_state.yes_mid) * 10000
        if spread_bps > self.spread_threshold_bps:
            logger.warning(f"Spread too wide: {spread_bps:.1f}bps > {self.spread_threshold_bps}bps")
            return False

        return True

    def get_next_execution_time(
        self,
        slices: List[ExecutionSlice],
        current_time: datetime,
    ) -> Optional[datetime]:
        """Get next execution time

        Args:
            slices: Execution plan slices
            current_time: Current time

        Returns:
            Next execution time, or None if none due
        """
        pending = [s for s in slices if s.target_time > current_time]
        if pending:
            return min(s.target_time for s in pending)
        return None

    def adjust_execution_plan(
        self,
        plan: ExecutionPlan,
        market_conditions: Dict,
    ) -> ExecutionPlan:
        """Adjust execution plan based on market conditions

        Args:
            plan: Current execution plan
            market_conditions: Market condition metrics

        Returns:
            Adjusted execution plan
        """
        volatility = market_conditions.get('volatility', 0.0)
        volume = market_conditions.get('volume', 1000)

        # Slow down in high volatility
        if volatility > 0.3:
            new_duration = int(plan.duration_seconds * 1.5)
            logger.info(f"Slowing execution due to high volatility ({volatility:.1%})")
        # Speed up in high volume
        elif volume > 5000:
            new_duration = int(plan.duration_seconds * 0.75)
            logger.info(f"Speeding up execution due to high volume ({volume})")
        else:
            return plan

        # Recalculate slice times
        time_step = new_duration / len(plan.slices)
        now = datetime.utcnow()

        new_slices = []
        for i, slice in enumerate(plan.slices):
            new_slice = ExecutionSlice(
                slice_id=slice.slice_id,
                contracts=slice.contracts,
                target_time=now + timedelta(seconds=i * time_step),
                min_price=slice.min_price,
                max_price=slice.max_price,
            )
            new_slices.append(new_slice)

        plan.slices = new_slices
        plan.duration_seconds = new_duration

        return plan
