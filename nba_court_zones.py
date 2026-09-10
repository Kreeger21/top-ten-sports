"""Reusable NBA half-court shot-zone classification.

Coordinates are feet from the center of the rim: x is lateral (negative left)
and y points toward half court. Source adapters should convert their native
coordinate units before calling this module.
"""

from math import hypot


def classify_shot(x, y):
    x, y = float(x), float(y)
    distance = hypot(x, y)
    side = "left" if x < -1.5 else "right" if x > 1.5 else "center"
    if distance <= 4:
        return "rim"
    if abs(x) <= 8 and y <= 19:
        return "paint"
    if distance >= 27:
        return f"deep-three-{side}"
    if abs(x) >= 22 and y <= 14:
        return "left-corner-three" if x < 0 else "right-corner-three"
    if distance >= 23.75:
        return f"above-break-three-{side}"
    if distance <= 14:
        return f"short-midrange-{side}"
    if y <= 8:
        return "left-baseline-midrange" if x < 0 else "right-baseline-midrange"
    if 6 <= abs(x) <= 14 and 8 < y <= 18:
        return "left-elbow" if x < 0 else "right-elbow"
    return f"long-midrange-{side}"
