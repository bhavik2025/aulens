"""Transaction costs for MCX non-agri futures.

Statutory rates (as published by brokers, e.g. Rupeezy support, 2025-26; re-check before use):
  exchange transaction charge 0.0021% each side, CTT 0.01% sell side, stamp duty 0.002% buy side,
  SEBI fee Rs 10 per crore, GST 18% on (brokerage + exchange charge + SEBI fee).
"""
from dataclasses import dataclass, field


@dataclass
class CostModel:
    exch: float = 0.0021 / 100
    ctt_sell: float = 0.01 / 100
    stamp_buy: float = 0.002 / 100
    sebi: float = 10 / 1e7
    gst: float = 0.18
    brokerage_per_order: float = 20.0
    # slippage vs settlement price, in basis points per side; thin contracts pay more
    slippage_bps: dict = field(default_factory=lambda: {"GOLDM": 0.5, "GOLDTEN": 1.5, "GOLDGUINEA": 3.0, "GOLDPETAL": 3.0})

    def side_cost(self, notional: float, side: str, symbol: str) -> float:
        """Cost in rupees of one buy or sell of `notional` rupees."""
        exch, sebi = notional * self.exch, notional * self.sebi
        tax = notional * (self.ctt_sell if side == "sell" else self.stamp_buy)
        gst = self.gst * (exch + sebi + self.brokerage_per_order)
        slip = notional * self.slippage_bps.get(symbol, 2.0) / 1e4
        return exch + sebi + tax + gst + self.brokerage_per_order + slip

    def round_trip_statutory_bps(self) -> float:
        """Statutory cost (no brokerage, no slippage) of buy+sell, in bps of notional."""
        per = 2 * self.exch + self.ctt_sell + self.stamp_buy + 2 * self.sebi
        per += self.gst * (2 * self.exch + 2 * self.sebi)
        return per * 1e4
