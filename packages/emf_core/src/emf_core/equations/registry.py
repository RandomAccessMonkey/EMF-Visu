from __future__ import annotations

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
            views.append(EquationView(
                **e.model_dump(exclude={"symbols"}),
                symbols=[self._symbols[s] for s in e.symbols],
                status=status, status_reason=reason,
                evaluated_by_solver=e.id in ctx.evaluated_equation_ids,
            ))
        return views

    def statuses(self, ctx: ModelContext) -> list[EquationStatusEntry]:
        return [EquationStatusEntry(equation_id=v.id, status=v.status, reason=v.status_reason)
                for v in self.evaluate(ctx)]


def default_registry() -> EquationRegistry:
    return EquationRegistry(EQUATIONS, SYMBOLS, RULES)
