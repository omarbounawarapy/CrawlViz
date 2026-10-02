"""Frozen-graph benchmark: run traversal policies through the real pipelines
on a graph that never changes, and compare what they fetch.

See benchmark/README.md.
"""
from .graph import FrozenGraph, synthetic_graph
from .policies import POLICIES
from .runner import RunResult, run_policy

__all__ = ["FrozenGraph", "synthetic_graph", "POLICIES", "RunResult", "run_policy"]
