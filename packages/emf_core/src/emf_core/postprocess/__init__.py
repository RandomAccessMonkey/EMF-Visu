"""Derived geometric products computed from a solver's field evaluator.

Nothing in this package evaluates physics: every field or potential value comes from the
evaluator callables handed in by the solver. These modules add numerical *methods* (ODE
integration, iso-contour extraction) whose accuracy is reported separately from the accuracy of
the underlying field."""
