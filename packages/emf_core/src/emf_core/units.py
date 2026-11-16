"""SI constants and quantity metadata. Every transported value carries one of these units."""

from __future__ import annotations

import math
from dataclasses import dataclass

# CODATA 2018 recommended values (SI).
C0: float = 299_792_458.0  # speed of light in vacuum, m/s (exact)
MU0: float = 1.256_637_062_12e-6  # vacuum permeability, H/m
EPS0: float = 8.854_187_812_8e-12  # vacuum permittivity, F/m
COULOMB_K: float = 1.0 / (4.0 * math.pi * EPS0)  # 1/(4*pi*eps0), N*m^2/C^2


@dataclass(frozen=True)
class QuantityInfo:
    key: str
    symbol: str
    unit: str
    rank: int  # 0 = scalar, 1 = vector


QUANTITIES: dict[str, QuantityInfo] = {
    q.key: q
    for q in (
        QuantityInfo("E", "E", "V/m", 1),
        QuantityInfo("phi", "φ", "V", 0),
        QuantityInfo("D", "D", "C/m^2", 1),
        # Pointwise divergence and curl (Phase 2B-1). Units: [E]/m and [D]/m.
        QuantityInfo("div_E", "∇·E", "V/m^2", 0),
        QuantityInfo("curl_E", "∇×E", "V/m^2", 1),
        QuantityInfo("div_D", "∇·D", "C/m^3", 0),
        QuantityInfo("curl_D", "∇×D", "C/m^3", 1),
        QuantityInfo("B", "B", "T", 1),
        QuantityInfo("H", "H", "A/m", 1),
        QuantityInfo("J", "J", "A/m^2", 1),
        QuantityInfo("S", "S", "W/m^2", 1),
        QuantityInfo("u", "u", "J/m^3", 0),
        QuantityInfo("rho_free", "ρ_free", "C/m^3", 0),
    )
}
