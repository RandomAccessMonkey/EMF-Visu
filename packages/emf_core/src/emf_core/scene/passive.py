"""Instantaneous state of a passive conducting circuit as a current filament (Phase 4C).

Produced by the circuit solver (``circuits.py``) at a simulation time and passed back with field
requests so the magnetic solver adds the field of the induced currents to the prescribed one.
The current is the solved induced current per turn; nothing here is a prescribed source."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ._base import FiniteFloat, PositiveFloat, StrictModel

Vec = tuple[FiniteFloat, FiniteFloat, FiniteFloat]


class PassiveFilament(StrictModel):
    id: str = Field(min_length=1, max_length=60)
    kind: Literal["circle", "polygon"]
    center_m: Vec
    normal: Vec = (0.0, 0.0, 1.0)  # circle: positive current counter-clockwise about it
    u: Vec = (1.0, 0.0, 0.0)  # circle: in-plane reference direction
    radius_m: PositiveFloat | None = None  # circle
    vertices_m: list[Vec] = Field(default=[], max_length=64)  # polygon, traversal order (world)
    turns: int = Field(default=1, ge=1, le=100_000)
    current_A: FiniteFloat = 0.0  # induced current per turn (from the circuit solution)
    rate_A_per_s: FiniteFloat = 0.0  # its time derivative (from the circuit solution)
    moving: bool = False  # the circuit moves at this instant (its dB/dt, E_ind need ∂A/∂t)
    wire_radius_m: PositiveFloat | None = None  # finite conductor size (for the probe status)
