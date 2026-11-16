from __future__ import annotations

from typing import Literal

from ..i18n import L
from ..solvers.base import EquationStatusEntry, ModelContext
from .data import EQUATIONS, SYMBOLS
from .models import Equation, EquationView, Rule, SymbolDef
from .rules import RULES


class EquationRegistry:
    def __init__(self, equations: list[Equation], symbols: dict[str, SymbolDef],
                 rules: dict[str, Rule]) -> None:
        ids = [e.id for e in equations]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate equation id")
        if set(ids) != set(rules):
            raise ValueError("every equation needs exactly one applicability rule")
        for e in equations:
            missing = [s for s in e.symbols if s not in symbols]
            if missing:
                raise ValueError(f"equation '{e.id}' uses undefined symbols {missing}")
        self._equations, self._symbols, self._rules = equations, symbols, rules

    @property
    def ids(self) -> list[str]:
        return [e.id for e in self._equations]

    def evaluate(self, ctx: ModelContext) -> list[EquationView]:
        views: list[EquationView] = []
        for e in self._equations:
            status, reason = self._rules[e.id](ctx)
            if status != "applicable" and reason is None:
                raise ValueError(f"rule for '{e.id}' returned '{status}' without a reason")
            evaluated = e.id in ctx.evaluated_equation_ids
            usage: Literal["evaluated", "checked", "satisfied", "not_used"]
            checked = e.id in ctx.checked_equation_ids
            if checked and status in ("applicable", "applicable_under_assumptions"):
                usage, note = "checked", L(
                    "Both sides are computed by independent methods (the surface integral from the "
                    "field over the oriented surface, the other side from the enclosed charges) "
                    "and compared in the flux results.",
                    "Mindkét oldalt független módszerrel számítja a program (a felületi integrált "
                    "a mezőből az irányított felületen, a másik oldalt a bezárt töltésekből), és "
                    "a fluxuseredményekben összeveti őket.")
            elif evaluated:
                usage, note = "evaluated", L(
                    "Evaluated directly by the active solver to produce the displayed fields.",
                    "Az aktív megoldó közvetlenül kiértékeli a megjelenített mezők előállításához.")
            elif status in ("applicable", "applicable_under_assumptions"):
                usage, note = "satisfied", L(
                    "A law or relation that the computed field satisfies. The active solver does "
                    "not solve this equation: no boundary-value problem is solved and no "
                    "independent numerical solution of it is produced.",
                    "Olyan törvény vagy összefüggés, amelyet a számított mező kielégít. Az aktív "
                    "megoldó ezt az egyenletet nem oldja meg: nem old meg peremérték-feladatot, "
                    "és nem állít elő hozzá független numerikus megoldást.")
            else:
                usage, note = "not_used", L(
                    "Not used by the active model.", "Az aktív modell nem használja.")
            views.append(EquationView(
                **e.model_dump(exclude={"symbols"}),
                symbols=[self._symbols[s] for s in e.symbols],
                status=status, status_reason=reason,
                evaluated_by_solver=evaluated, usage=usage, usage_note=note,
            ))
        return views

    def statuses(self, ctx: ModelContext) -> list[EquationStatusEntry]:
        return [EquationStatusEntry(equation_id=v.id, status=v.status, reason=v.status_reason)
                for v in self.evaluate(ctx)]


def default_registry() -> EquationRegistry:
    return EquationRegistry(EQUATIONS, SYMBOLS, RULES)
