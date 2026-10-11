"""Portable binding validation and Windows virtual-key names."""

from dataclasses import dataclass

MODIFIERS = ("ctrl", "shift")
KEY_VKS = {chr(n).lower(): n for n in range(65, 91)}
KEY_VKS.update({str(n): 48 + n for n in range(10)})
KEY_VKS.update({f"f{n}": 111 + n for n in range(1, 13)})
KEY_VKS.update({
    "space": 0x20, "tab": 0x09, "backspace": 0x08,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26,
    "right": 0x27, "down": 0x28, "minus": 0xBD, "equals": 0xBB,
    "leftbracket": 0xDB, "rightbracket": 0xDD, "backslash": 0xDC,
    "semicolon": 0xBA, "apostrophe": 0xDE, "comma": 0xBC, "period": 0xBE,
})
VK_NAMES = {value: key for key, value in KEY_VKS.items()}
VK_NAMES.update({0x0D: "enter", 0x1B: "escape", 0xBF: "slash", 0xC0: "backquote"})
MODIFIER_VKS = {
    0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
    0x12: "alt", 0xA4: "alt", 0xA5: "alt",
    0x5B: "win", 0x5C: "win",
}
ALIASES = {"control": "ctrl", "mouse4": "mouse4", "xbutton1": "mouse4",
           "mouse5": "mouse5", "xbutton2": "mouse5", "pgup": "pageup",
           "pgdn": "pagedown", "return": "enter", "esc": "escape",
           "-": "minus", "=": "equals", "[": "leftbracket", "]": "rightbracket",
           "\\": "backslash", ";": "semicolon", "'": "apostrophe",
           ",": "comma", ".": "period", "/": "slash", "`": "backquote"}
RESERVED = {"f10", "f12", "enter", "escape", "slash", "backquote"}


@dataclass(frozen=True)
class Binding:
    key: str
    modifiers: frozenset[str] = frozenset()

    def __str__(self) -> str:
        return "+".join([m for m in MODIFIERS if m in self.modifiers] + [self.key])


def parse_binding(value: str) -> Binding | None:
    if not isinstance(value, str):
        raise ValueError("Bindings must be text.")
    if not value.strip() or value.strip().lower() == "unbound":
        return None
    parts = [ALIASES.get(p.strip().lower(), p.strip().lower()) for p in value.split("+")]
    if not parts or any(not p for p in parts):
        raise ValueError("Use a key or a combination such as Ctrl+Shift+Q.")
    key, mods = parts[-1], parts[:-1]
    if key in RESERVED:
        raise ValueError(f"{key.upper()} is reserved for safety or text protection.")
    if key not in KEY_VKS and key not in {"mouse4", "mouse5"}:
        raise ValueError(f"Unsupported key: {key}. Use Record or see the README.")
    if any(m not in MODIFIERS for m in mods) or len(mods) != len(set(mods)):
        raise ValueError("Only Ctrl and Shift modifiers are supported (each once).")
    return Binding(key, frozenset(mods))


def validate_bindings(values: list[str] | tuple[str, ...]) -> tuple[Binding | None, ...]:
    if len(values) != 9:
        raise ValueError("Exactly nine hotbar bindings are required.")
    bindings = []
    for slot, value in enumerate(values, 1):
        try:
            bindings.append(parse_binding(value))
        except ValueError as error:
            raise ValueError(f"Slot {slot}: {error}") from error
    duplicates = duplicate_bindings(bindings)
    if duplicates:
        details = "; ".join(f"{key}: slots {', '.join(map(str, slots))}" for key, slots in duplicates.items())
        raise ValueError(f"Duplicate bindings — {details}. Each input needs one slot.")
    return tuple(bindings)


def duplicate_bindings(bindings) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for slot, binding in enumerate(bindings, 1):
        if binding is not None:
            groups.setdefault(str(binding), []).append(slot)
    return {key: slots for key, slots in groups.items() if len(slots) > 1}
