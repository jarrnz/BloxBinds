"""Calibrated manual Inventory Mode; no access to Roblox inventory state."""

import json
import re
from dataclasses import dataclass
from threading import RLock

from .settings import save_json


@dataclass(frozen=True)
class Geometry:
    hwnd: int
    pid: int
    left: int
    top: int
    width: int
    height: int
    dpi: int

    @property
    def signature(self):
        return self.width, self.height, self.dpi

    def relative(self, point):
        return point[0] - self.left, point[1] - self.top

    def absolute(self, point):
        return point[0] + self.left, point[1] + self.top


@dataclass(frozen=True)
class Calibration:
    size: tuple[int, int, int]
    region: tuple[int, int, int, int]
    slots: tuple[tuple[int, int], ...]
    empty_hashes: tuple[str | None, ...] = ()

    def validate(self):
        if len(self.size) != 3 or any(type(v) is not int for v in self.size):
            raise ValueError("Invalid calibrated size/DPI.")
        width, height, dpi = self.size
        if not (320 <= width <= 16384 and 240 <= height <= 16384 and 48 <= dpi <= 768):
            raise ValueError("Invalid calibrated size/DPI.")
        if len(self.region) != 4 or any(type(v) is not int for v in self.region):
            raise ValueError("Invalid inventory item area.")
        x1, y1, x2, y2 = self.region
        if not (8 <= x1 < x2 <= width - 8 and 8 <= y1 < y2 <= height - 8 and
                x2 - x1 >= 16 and y2 - y1 >= 16):
            raise ValueError("Mark the item-grid top-left, then bottom-right, inside the client.")
        if len(self.slots) != 9:
            raise ValueError("Calibrate all nine slot centers.")
        for i, point in enumerate(self.slots):
            if len(point) != 2 or any(type(v) is not int for v in point):
                raise ValueError("Invalid slot center.")
            x, y = point
            if not (8 <= x < width - 8 and 8 <= y < height - 8):
                raise ValueError("Slot centers must be safely inside the client.")
            if x1 <= x <= x2 and y1 <= y <= y2:
                raise ValueError("The item area must exclude the hotbar and search box.")
            if any((x - a)**2 + (y - b)**2 < 100 for a, b in self.slots[:i]):
                raise ValueError("Slot centers must be distinct.")
        if self.empty_hashes and (len(self.empty_hashes) != 9 or any(
                h is not None and (not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h))
                for h in self.empty_hashes)):
            raise ValueError("Invalid empty-slot references.")
        return self

    @property
    def radius(self):
        distance = min(((x-a)**2 + (y-b)**2)**0.5 for i, (x,y) in enumerate(self.slots)
                       for a,b in self.slots[i+1:])
        return max(4, min(40, int(distance/2)-4,
                          *(min(x, y, self.size[0]-x, self.size[1]-y)-2 for x,y in self.slots)))

    def contains(self, point):
        x1, y1, x2, y2 = self.region
        return x1 + 4 <= point[0] <= x2 - 4 and y1 + 4 <= point[1] <= y2 - 4

    def to_dict(self):
        self.validate()
        return {"version": 1, "size": self.size, "region": self.region, "slots": self.slots, "empty_hashes": self.empty_hashes}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or type(data.get("version")) is not int or data['version'] != 1:
            raise ValueError("Unsupported calibration format.")
        try:
            return cls(tuple(data['size']), tuple(data['region']),
                       tuple(tuple(p) for p in data['slots']), tuple(data.get("empty_hashes", ()))).validate()
        except (KeyError, TypeError) as error:
            raise ValueError("Invalid calibration data.") from error


def load_calibration(path):
    try:
        return Calibration.from_dict(json.loads(path.read_text(encoding='utf-8'))), None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError, TypeError) as error:
        return None, f"Calibration ignored: {error}"


def save_calibration(path, profile):
    save_json(path, profile.to_dict())


@dataclass(frozen=True)
class Move:
    geometry: Geometry
    source: tuple[int, int]
    target: tuple[int, int]
    epoch: int
    engine_generation: int
    empty_hash: str
    radius: int


class QuickMove:
    """Explicit manual backpack assertion, never automatic inventory detection."""
    def __init__(self, profile=None):
        self.lock = RLock()
        self.profile = profile
        self.enabled = False
        self.compatibility = "Unknown"  # Verification never carries into a new game/session.
        self.shortcut = "ctrl+shift+f6"
        self.active = False
        self.geometry = None
        self.epoch = 0
        self.busy = False
        self.used = set()
        self.calibrating = False
        self.points = []
        self.capture_geometry = None
        self.empty_slots = ({i+1 for i,h in enumerate(profile.empty_hashes) if h} if profile and any(profile.empty_hashes) else {9})

    def cancel(self):
        with self.lock:
            self.epoch += 1
            self.active = False
            self.geometry = None
            self.busy = False

    def enable(self, value):
        with self.lock:
            self.cancel()
            self.enabled = bool(value)

    def set_compatibility(self, value):
        if value not in ("Unknown", "Compatible", "Unsupported"):
            raise ValueError("Invalid inventory compatibility.")
        with self.lock:
            self.cancel()
            self.compatibility = value

    def activate(self, geometry):
        with self.lock:
            self.cancel()
            if not self.enabled or self.compatibility != "Compatible":
                raise ValueError("Enable Quick-Move and verify built-in backpack compatibility first.")
            if self.calibrating or not self.profile or not any(self.profile.empty_hashes):
                raise ValueError("Needs Calibration: record visibly empty target slots first.")
            if self.profile.size != geometry.signature:
                raise ValueError("Needs Calibration: window size/DPI changed.")
            self.active = True
            self.geometry = geometry

    def begin_calibration(self, refresh=False):
        with self.lock:
            self.cancel()
            self.calibrating = True
            self.points = []
            self.capture_geometry = None
            if refresh and self.profile:
                self.profile = Calibration(self.profile.size,self.profile.region,self.profile.slots)
                self.points = [self.profile.region[:2], self.profile.region[2:], *self.profile.slots]
                return "Hover clear space in the open item grid and CLICK to record marked EMPTY slots."
            self.profile = None
            return "CLICK item-grid TOP-LEFT (exclude search, chat and hotbar). Clicks are captured."

    def capture(self, geometry, cursor):
        with self.lock:
            if not self.calibrating:
                raise ValueError("Calibration is not active.")
            if self.capture_geometry is None:
                self.capture_geometry = geometry
            if geometry != self.capture_geometry:
                self.points = []
                self.capture_geometry = None
                raise ValueError("Window changed during calibration. Start again at the top-left.")
            if len(self.points) == 11:
                if self.profile.size != geometry.signature or not self.profile.contains(geometry.relative(cursor)):
                    raise ValueError("Hover clear space inside the item grid, away from target slots, then click.")
                self.calibrating = False
                self.points = []
                return "Recording empty-slot appearance; remapping remains OFF.", self.profile
            self.points.append(geometry.relative(cursor))
            if len(self.points) == 1:
                return "CLICK item-grid BOTTOM-RIGHT (exclude text fields).", None
            if len(self.points) < 11:
                return f"CLICK hotbar slot {len(self.points)-1} CENTER.", None
            try:
                a, b = self.points[:2]
                self.profile = Calibration(geometry.signature, (*a, *b), tuple(self.points[2:])).validate()
                return "Now CLICK clear space inside the item grid to record marked EMPTY slots.", None
            except ValueError:
                self.points = []
                self.capture_geometry = None
                self.profile = None
                raise

    def take(self, slot, geometry, cursor, generation):
        with self.lock:
            if not self.active or self.busy or self.calibrating or not 1 <= slot <= 9:
                return None
            if (not self.enabled or self.compatibility != "Compatible" or geometry != self.geometry or
                    not self.profile or geometry.signature != self.profile.size):
                self.cancel()
                return None
            if not self.profile.contains(geometry.relative(cursor)) or slot in self.used:
                return None
            reference = self.profile.empty_hashes[slot-1] if self.profile.empty_hashes else None
            if reference is None:
                return None
            self.busy = True
            self.used.add(slot)  # Never reuse an attempted target without explicitly refreshing emptiness.
            return Move(geometry, cursor, geometry.absolute(self.profile.slots[slot-1]),
                        self.epoch, generation, reference, self.profile.radius)

    def valid(self, move):
        with self.lock:
            return self.enabled and self.active and self.compatibility == "Compatible" and self.busy and self.epoch == move.epoch

    def complete(self, move):
        with self.lock:
            if self.epoch == move.epoch:
                self.busy = False

    def status(self, *, focused=True, remapping=True, geometry=None):
        with self.lock:
            if self.calibrating:
                return "Calibration active: click each requested point in Roblox."
            if not self.enabled or not remapping:
                return "Disabled"
            if not focused:
                return "Roblox Not Focused"
            if self.compatibility == "Unsupported":
                return "Unsupported"
            if self.compatibility != "Compatible":
                return "Compatibility Unknown"
            if not self.profile or not any(self.profile.empty_hashes) or (geometry and geometry.signature != self.profile.size):
                return "Needs Calibration"
            if not self.active:
                return "Inventory Mode Off"
            if not any(h and i+1 not in self.used for i,h in enumerate(self.profile.empty_hashes)):
                return "No verified empty targets — refresh empty slots"
            return "Ready (manual / experimental)"
