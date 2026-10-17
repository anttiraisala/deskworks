"""Rectangle type shared by every module (pixels, origin at the top left)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom

    def distance_sq(self, px: float, py: float) -> float:
        """Squared distance from a point to the rectangle (0 when inside)."""
        dx = max(self.x - px, 0, px - (self.right - 1))
        dy = max(self.y - py, 0, py - (self.bottom - 1))
        return dx * dx + dy * dy

    def intersect(self, other: "Rect") -> "Rect":
        """The overlapping part; width and height are 0 when there is none."""
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        return Rect(left, top, max(0, right - left), max(0, bottom - top))

    def to_list(self) -> List[int]:
        return [self.x, self.y, self.width, self.height]

    @staticmethod
    def from_list(values) -> "Rect":
        x, y, width, height = (int(v) for v in values)
        return Rect(x, y, width, height)

    def __str__(self) -> str:
        return "%dx%d%+d%+d" % (self.width, self.height, self.x, self.y)
