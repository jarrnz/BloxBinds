"""Pure input state machine, separated from hooks and Tk for testing."""

from dataclasses import dataclass
from threading import RLock

from .keys import Binding, validate_bindings
from .settings import Settings


@dataclass(frozen=True)
class Decision:
    suppress: bool = False
    slot: int | None = None
    generation: int = 0


class Engine:
    def __init__(self, settings: Settings):
        self.lock = RLock()
        self.enabled = False
        self.closed = False
        self.text_paused = False
        self.pause_key = None
        self.generation = 0
        self.held: set[str] = set()
        self.suppressed: set[str] = set()
        self.apply(settings)

    def apply(self, settings: Settings):
        settings.validate()
        with self.lock:
            self.settings = settings
            self.mapping = {binding: slot for slot, binding in
                            enumerate(validate_bindings(settings.bindings), 1) if binding}
            self.enabled = False
            self.generation += 1

    def enable(self, enabled: bool):
        with self.lock:
            self.enabled = bool(enabled and not self.closed and
                                self.settings.compatibility != "Unsupported")
            self.generation += 1
            return self.enabled

    def close(self):
        with self.lock:
            self.closed = True
            self.enabled = False
            self.generation += 1

    def focus_lost(self):
        # Keep consumed key-ups balanced, but invalidate queued output.
        with self.lock:
            self.generation += 1

    def allowed(self, generation: int, focused: bool, native_text: bool = False):
        with self.lock:
            return (not self.closed and self.enabled and focused and
                    not self.text_paused and generation == self.generation and
                    not (self.settings.protect_text and native_text))

    def process(self, key: str, down: bool, modifiers=frozenset(), *,
                focused=False, injected=False, native_text=False, quick_move=False) -> Decision:
        with self.lock:
            if injected or self.closed:
                return Decision()
            if not down:
                self.held.discard(key)
                consumed = key in self.suppressed
                self.suppressed.discard(key)
                return Decision(consumed)
            repeated = key in self.held
            self.held.add(key)
            if repeated:
                return Decision(key in self.suppressed)
            if key == "f12" and {"ctrl", "alt"}.issubset(modifiers):
                self.enable(False)
                self.suppressed.add(key)
                return Decision(True)
            if not focused:
                return Decision()
            if key == "f10":
                self.text_paused = not self.text_paused
                self.pause_key = None
                self.generation += 1
                self.suppressed.add(key)
                return Decision(True)
            if self.settings.protect_text and key in {"enter", "slash", "backquote"}:
                self.text_paused = True
                self.pause_key = key
                self.generation += 1
                return Decision()
            if not self.allowed(self.generation, focused, native_text):
                return Decision()
            slot = self.mapping.get(Binding(key, frozenset(modifiers)))
            if slot is None:
                return Decision()
            # Identity bindings need no synthetic input or suppression.
            if key == str(slot) and not modifiers and not quick_move:
                return Decision()
            self.suppressed.add(key)
            return Decision(True, slot, self.generation)
