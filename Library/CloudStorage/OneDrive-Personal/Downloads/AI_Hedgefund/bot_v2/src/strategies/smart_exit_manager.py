"""Smart Exit Manager - Close positions at profit targets, stops, trailing stops"""

import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class OpenPosition:
    """Track an open position"""
    position_id: str
    market_id: str
    side: str  # BUY or SELL
    entry_price: float
    entry_time: float
    contracts: int

    current_price: float = field(default=0.0)
    highest_price: float = field(default=0.0)
    lowest_price: float = field(default=0.0)

    exit_reason: Optional[str] = None
    exit_price: Optional[float] = None


@dataclass
class ExitSignal:
    """Signal to exit a position"""
    position_id: str
    reason: str  # "profit_target", "stop_loss", "trailing_stop", "time_limit"
    exit_price: float
    expected_pnl: float


class SmartExitManager:
    """Manage exits with profit targets, stops, trailing stops"""

    def __init__(
        self,
        profit_target_pct: float = 2.0,
        stop_loss_pct: float = 1.0,
        trailing_stop_pct: float = 1.5,
        time_limit_hours: float = 24,
    ):
        """
        Initialize exit manager

        Args:
            profit_target_pct: Close at this % profit (default 2%)
            stop_loss_pct: Close at this % loss (default 1%)
            trailing_stop_pct: Trailing stop distance (default 1.5%)
            time_limit_hours: Max hold time (default 24h)
        """
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.time_limit_hours = time_limit_hours

        self.open_positions: Dict[str, OpenPosition] = {}
        self.exit_history: List[Dict] = []

        logger.info(
            f"SmartExitManager initialized: "
            f"profit_target={profit_target_pct}%, "
            f"stop_loss={stop_loss_pct}%, "
            f"trailing_stop={trailing_stop_pct}%"
        )

    def open_position(
        self,
        position_id: str,
        market_id: str,
        side: str,
        entry_price: float,
        entry_time: float,
        contracts: int,
    ):
        """Open a new position"""
        pos = OpenPosition(
            position_id=position_id,
            market_id=market_id,
            side=side,
            entry_price=entry_price,
            entry_time=entry_time,
            contracts=contracts,
            current_price=entry_price,
            highest_price=entry_price,
            lowest_price=entry_price,
        )
        self.open_positions[position_id] = pos
        logger.info(f"Opened position {position_id}: {side} {contracts} @ {entry_price}")

    def update_price(self, position_id: str, current_price: float, current_time: float):
        """Update position price"""
        if position_id not in self.open_positions:
            return

        pos = self.open_positions[position_id]
        pos.current_price = current_price
        pos.highest_price = max(pos.highest_price, current_price)
        pos.lowest_price = min(pos.lowest_price, current_price)

    def check_exits(self, current_time: float, current_prices: Dict[str, float]) -> List[ExitSignal]:
        """Check if any positions should exit"""
        exit_signals = []

        for pos_id, position in list(self.open_positions.items()):
            if pos_id not in current_prices:
                continue

            current_price = current_prices[pos_id]
            self.update_price(pos_id, current_price, current_time)

            # Check exit conditions
            signal = self._check_position_exits(position, current_price, current_time)
            if signal:
                exit_signals.append(signal)

        return exit_signals

    def _check_position_exits(
        self,
        position: OpenPosition,
        current_price: float,
        current_time: float,
    ) -> Optional[ExitSignal]:
        """Check if a position should exit"""

        if position.side == "BUY":
            return_pct = (current_price - position.entry_price) / position.entry_price * 100
        else:
            return_pct = (position.entry_price - current_price) / position.entry_price * 100

        # Check 1: Profit target
        if return_pct >= self.profit_target_pct:
            return ExitSignal(
                position_id=position.position_id,
                reason="profit_target",
                exit_price=current_price,
                expected_pnl=(current_price - position.entry_price) * position.contracts,
            )

        # Check 2: Stop loss
        if return_pct <= -self.stop_loss_pct:
            return ExitSignal(
                position_id=position.position_id,
                reason="stop_loss",
                exit_price=current_price,
                expected_pnl=(current_price - position.entry_price) * position.contracts,
            )

        # Check 3: Trailing stop
        if position.side == "BUY":
            trailing_stop_price = position.highest_price * (1 - self.trailing_stop_pct / 100)
            if current_price <= trailing_stop_price:
                return ExitSignal(
                    position_id=position.position_id,
                    reason="trailing_stop",
                    exit_price=current_price,
                    expected_pnl=(current_price - position.entry_price) * position.contracts,
                )

        # Check 4: Time limit
        hours_held = (current_time - position.entry_time) / 3600
        if hours_held >= self.time_limit_hours:
            return ExitSignal(
                position_id=position.position_id,
                reason="time_limit",
                exit_price=current_price,
                expected_pnl=(current_price - position.entry_price) * position.contracts,
            )

        return None

    def close_position(self, position_id: str, exit_price: float, exit_reason: str) -> Optional[Dict]:
        """Close a position"""
        if position_id not in self.open_positions:
            return None

        position = self.open_positions[position_id]
        pnl = (exit_price - position.entry_price) * position.contracts
        return_pct = (exit_price - position.entry_price) / position.entry_price * 100

        result = {
            "position_id": position_id,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "return_pct": return_pct,
            "exit_reason": exit_reason,
        }

        self.exit_history.append(result)
        del self.open_positions[position_id]

        logger.info(f"Closed {position_id}: {exit_reason} @ {exit_price}, P&L=${pnl:.2f}")

        return result

    def get_stats(self) -> Dict:
        """Get exit statistics"""
        if not self.exit_history:
            return {"closed_trades": 0}

        reasons = {}
        for trade in self.exit_history:
            reason = trade["exit_reason"]
            if reason not in reasons:
                reasons[reason] = []
            reasons[reason].append(trade["pnl"])

        stats = {
            "closed_trades": len(self.exit_history),
            "total_pnl": sum(t["pnl"] for t in self.exit_history),
            "exits_by_reason": {},
        }

        for reason, pnls in reasons.items():
            stats["exits_by_reason"][reason] = {
                "count": len(pnls),
                "total_pnl": sum(pnls),
                "avg_pnl": sum(pnls) / len(pnls),
            }

        return stats

    def get_open_positions_summary(self) -> str:
        """Get summary of open positions"""
        if not self.open_positions:
            return "No open positions"

        summary = f"\n{'='*60}\nOPEN POSITIONS ({len(self.open_positions)})\n{'='*60}\n"

        for pos_id, pos in self.open_positions.items():
            return_pct = (pos.current_price - pos.entry_price) / pos.entry_price * 100
            summary += f"{pos.market_id} ({pos.side}): {pos.contracts} @ {pos.entry_price}\n"
            summary += f"  Current: {pos.current_price} ({return_pct:+.2f}%)\n"
            summary += f"  High: {pos.highest_price}, Low: {pos.lowest_price}\n\n"

        return summary
