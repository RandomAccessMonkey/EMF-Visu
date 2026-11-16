"""Solver-agnostic worker runtime. Every worker image = emf_core + emf_worker + the native
dependencies of its solvers, consuming one queue (``solver.<kind>``)."""

JOB_PROTOCOL_VERSION = 1
