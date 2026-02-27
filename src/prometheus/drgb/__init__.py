"""Dual Reality Guardian Bridge (DRGB) package."""

from .bridge import GuardianBridge, GuardianSignal
from .reality_stream import RealityStreamA, RealityStreamB
from .convergence import DefaultConvergenceStrategy

__all__ = [
    "GuardianBridge",
    "GuardianSignal",
    "RealityStreamA",
    "RealityStreamB",
    "DefaultConvergenceStrategy",
]
