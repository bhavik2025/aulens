"""Contract specifications for the MCX gold contracts in PS 03.

Source: Hack in Hills '26 PS 03 "Contract Mechanics" table. Verify against
https://www.mcxindia.com/products/bullion/gold before relying on them.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Spec:
    symbol: str
    lot_g: float      # grams per lot (trading unit)
    quote_g: float    # price is quoted per this many grams
    purity: int       # parts per thousand (995 / 999)

    @property
    def fine_factor(self) -> float:
        """Grams of fine gold per gram of contract metal."""
        return self.purity / 1000.0

    def lot_multiplier(self) -> float:
        """Rupee P&L per 1-rupee move in the quoted price, per lot."""
        return self.lot_g / self.quote_g


SPECS = {
    "GOLDM": Spec("GOLDM", 100, 10, 995),
    "GOLDTEN": Spec("GOLDTEN", 10, 10, 999),
    "GOLDGUINEA": Spec("GOLDGUINEA", 8, 8, 999),
    "GOLDPETAL": Spec("GOLDPETAL", 1, 1, 999),
}

# Pairs we analyse, with an equal-gram hedge (lots of A, lots of B).
# 1 GOLDM (100 g) = 10 GOLDTEN = 100 GOLDPETAL; 4 GOLDTEN (40 g) = 5 GOLDGUINEA (40 g).
PAIRS = {
    "GOLDM/GOLDTEN": ("GOLDM", "GOLDTEN", 1, 10),
    "GOLDM/GOLDPETAL": ("GOLDM", "GOLDPETAL", 1, 100),
    "GOLDTEN/GOLDGUINEA": ("GOLDTEN", "GOLDGUINEA", 4, 5),
    "GOLDTEN/GOLDPETAL": ("GOLDTEN", "GOLDPETAL", 1, 10),
    "GOLDGUINEA/GOLDPETAL": ("GOLDGUINEA", "GOLDPETAL", 1, 8),
    "GOLDM/GOLDGUINEA": ("GOLDM", "GOLDGUINEA", 2, 25),
}

GOLD_SYMBOLS = tuple(SPECS)
