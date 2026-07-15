"""Conversions between physical opening and the simulated closure command."""


def opening_to_closure(opening: float, maximum_opening: float) -> float:
    """Convert physical jaw opening to the simulation bridge closure travel."""

    if maximum_opening <= 0.0:
        raise ValueError("maximum_opening must be positive")
    if opening < 0.0 or opening > maximum_opening:
        raise ValueError("opening is outside the supported range")
    return maximum_opening - opening


def closure_to_opening(closure: float, maximum_opening: float) -> float:
    """Convert simulated closure travel to physical jaw opening."""

    if maximum_opening <= 0.0:
        raise ValueError("maximum_opening must be positive")
    bounded_closure = max(0.0, min(maximum_opening, closure))
    return maximum_opening - bounded_closure
