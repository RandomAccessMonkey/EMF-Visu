from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..i18n import LocalizedText
from ..solvers.base import ModelContext

EquationStatus = Literal[
    "applicable", "applicable_under_assumptions", "not_applicable", "not_evaluated"
]
Category = Literal["maxwell", "electrostatics", "magnetostatics", "induction", "constitutive",
                   "additional"]
# A rule maps the model context to (status, reason). The reason is mandatory for every status
# other than "applicable".
Rule = Callable[[ModelContext], tuple[EquationStatus, LocalizedText | None]]


class SymbolDef(BaseModel):
    latex: str
    meaning: LocalizedText
    unit: str  # SI unit; "1" for dimensionless, "" for operators


class Equation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    category: Category
    name: LocalizedText
    latex: str
    latex_integral: str | None = None
    meaning: LocalizedText
    intuition: LocalizedText
    symbols: list[str]  # keys into the shared symbol table
    assumptions: list[LocalizedText] = []
    limitations: list[LocalizedText] = []
    conditions: list[LocalizedText] = []  # boundary / initial conditions where relevant
    derivation: list[LocalizedText] = []  # optional step-by-step expansion
    used_by: list[str] = []  # solver ids whose implementation evaluates this equation
    # Usage note shown instead of the generic one when the equation is "satisfied" (Phase 3A).
    satisfied_note: LocalizedText | None = None
    # An idealized approximation (Phase 3B): shown for comparison, never the solver's result
    # unless the solver evaluates it in the active model.
    idealized: bool = False


class EquationView(BaseModel):
    """An equation resolved against a model context: what the frontend displays."""

    id: str
    category: Category
    name: LocalizedText
    latex: str
    latex_integral: str | None
    meaning: LocalizedText
    intuition: LocalizedText
    symbols: list[SymbolDef]
    assumptions: list[LocalizedText]
    limitations: list[LocalizedText]
    conditions: list[LocalizedText]
    derivation: list[LocalizedText]
    used_by: list[str]
    status: EquationStatus
    status_reason: LocalizedText | None
    evaluated_by_solver: bool
    # How the active solver relates to this equation, computed from the model context:
    #   evaluated      - its formula is evaluated directly to produce the displayed fields;
    #   satisfied      - it applies and the computed field obeys it, but the solver does not
    #                    solve it (no boundary-value problem or independent check is performed);
    #   checked        - both sides are computed by independent methods and compared;
    #   not_used       - it does not apply to, or is not evaluated in, the active model.
    usage: Literal["evaluated", "checked", "satisfied", "approximation", "not_used"]
    usage_note: LocalizedText
