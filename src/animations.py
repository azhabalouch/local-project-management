"""
A couple of small, purposeful animation helpers.

Kept deliberately minimal: the brief calls for animation only where it
earns its place (softening a state change so the eye can follow it), not
as decoration. Two cases use it in this app - a widget fading into place
(the welcome tour, the hint bar updating) and a quick "pulse" flash to
confirm an action landed (e.g. a successful save).
"""
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QObject
from PyQt6.QtWidgets import QGraphicsOpacityEffect


def fade_in(widget, duration: int = 220):
    """
    Fades `widget` in from transparent to opaque. Returns the animation
    object - callers should keep a reference (e.g. store it on self) so
    it isn't garbage-collected mid-flight.
    """
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim
