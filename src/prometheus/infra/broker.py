"""Broker interface and paper trading implementation.

BrokerInterface: abstract interface for real/paper brokers.
PaperBroker: logs hypothetical trades without real execution.

PLUG-IN POINT: Implement BrokerInterface for your real broker
(e.g., Kraken, Binance, Alpaca).
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Order:
    """Trade order."""

    order_id: str
    symbol: str
    side: str  # "buy" | "sell"
    quantity: float
    price: float
    timestamp: float = field(default_factory=time.time)
    status: str = "filled"  # pending | filled | cancelled
    metadata: dict[str, Any] = field(default_factory=dict)


class BrokerInterface(ABC):
    """Abstract broker interface.

    Implement this for real broker connections.
    """

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
        order_type: str = "market",
    ) -> Order:
        """Submit a trade order."""
        ...

    @abstractmethod
    def get_balance(self) -> dict[str, float]:
        """Get account balances."""
        ...

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        """Get open positions."""
        ...

    @abstractmethod
    def get_last_price(self, symbol: str) -> float:
        """Get last traded price for a symbol."""
        ...


class PaperBroker(BrokerInterface):
    """Paper trading broker that logs hypothetical trades.

    Tracks virtual balance and positions without real execution.
    """

    def __init__(
        self,
        initial_balance: float = 100_000.0,
        default_symbol: str = "BTC/USD",
    ) -> None:
        self._cash = initial_balance
        self._initial_balance = initial_balance
        self._positions: dict[str, float] = {}  # symbol -> quantity
        self._orders: list[Order] = []
        self._order_counter = 0
        self._last_prices: dict[str, float] = {}
        self._default_symbol = default_symbol

    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
        order_type: str = "market",
    ) -> Order:
        """Execute a paper trade."""
        self._order_counter += 1
        oid = f"PAPER-{self._order_counter:06d}"

        exec_price = price or self._last_prices.get(symbol, 0.0)

        if side == "buy":
            cost = quantity * exec_price
            if cost > self._cash:
                logger.warning("Insufficient funds: need %.2f, have %.2f", cost, self._cash)
                quantity = self._cash / exec_price if exec_price > 0 else 0
                cost = quantity * exec_price
            self._cash -= cost
            self._positions[symbol] = self._positions.get(symbol, 0) + quantity
        elif side == "sell":
            current = self._positions.get(symbol, 0)
            sell_qty = min(quantity, current)
            self._cash += sell_qty * exec_price
            self._positions[symbol] = current - sell_qty
            quantity = sell_qty

        order = Order(
            order_id=oid,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=exec_price,
        )
        self._orders.append(order)

        logger.info(
            "PAPER TRADE: %s %s %.6f %s @ $%.2f | Cash: $%.2f",
            oid,
            side.upper(),
            quantity,
            symbol,
            exec_price,
            self._cash,
        )
        return order

    def get_balance(self) -> dict[str, float]:
        equity = self._cash
        for sym, qty in self._positions.items():
            equity += qty * self._last_prices.get(sym, 0)
        return {
            "cash": self._cash,
            "equity": equity,
            "initial": self._initial_balance,
            "pnl": equity - self._initial_balance,
            "pnl_pct": (equity - self._initial_balance) / self._initial_balance,
        }

    def get_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": sym,
                "quantity": qty,
                "value": qty * self._last_prices.get(sym, 0),
            }
            for sym, qty in self._positions.items()
            if qty != 0
        ]

    def get_last_price(self, symbol: str) -> float:
        return self._last_prices.get(symbol, 0.0)

    def update_price(self, symbol: str, price: float) -> None:
        """Update last known price (called by data feed)."""
        self._last_prices[symbol] = price

    @property
    def order_history(self) -> list[Order]:
        return list(self._orders)
