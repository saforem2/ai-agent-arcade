"""Compatibility alias for the former Thunderdome module name."""

from .arcade_app import ArcadeApp, BrailleBoard, decision_history, main, score_line

Thunderdome = ArcadeApp

__all__ = [
    "ArcadeApp",
    "BrailleBoard",
    "Thunderdome",
    "decision_history",
    "main",
    "score_line",
]
