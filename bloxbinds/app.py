"""Compact Tk settings interface. All widgets stay on the Tk thread."""

import json
import queue
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .engine import Engine
from .quickmove import QuickMove, load_calibration, save_calibration
from .keys import parse_binding, validate_bindings
from .settings import COMPATIBILITIES, Settings, load_settings, save_settings, settings_path, save_json
from .win32 import InputService, SingleInstance, WindowsAPI
from .backup import export_settings, import_settings
from .startup import Startup
from .sound import Sounds
from .updates import UpdateChecker, Version, valid_release_url


class App:
    def __init__(self, root, *, api=None, service_factory=InputService, path=None, single_instance=True, tray_factory=None,
                 startup_factory=Startup, indicator_factory=None, sound_factory=Sounds):
        self.root = root
        self.path = path or settings_path()
        settings, warning = load_settings(self.path)
        # A previous session's manual verification is not evidence for a new game.
        if settings.compatibility == "Verified by me":
            settings = replace(settings, compatibility="Unknown")
        self.engine = Engine(settings)
        self.api = api or WindowsAPI()
        self.instance = SingleInstance(self.api) if single_instance else None
        self.service = service_factory(self.engine, self.api)
        self.startup = startup_factory()
        self.sounds = sound_factory()
        self.sounds.enabled = settings.sound_feedback
        self.updates = UpdateChecker(self.service.events, Version.parse(__version__ + "-beta"))
        self.indicator = None
        self._indicator_factory = indicator_factory
        self._features_dialog = None
        self._update_url = None
        self.update_status = tk.StringVar(value="Not checked. Network access is optional.")
        self._feature_vars = {}
        try:
            startup_warning = self.startup.repair(settings.launch_with_windows)
            if startup_warning:
                warning = startup_warning
        except OSError:
            warning = "Could not repair Windows startup. Re-enable startup from Options after extracting the app."
        self.calibration_path = self.path.with_name("quickmove.json")
        profile, calibration_warning = load_calibration(self.calibration_path)
        self.quickmove = QuickMove(profile)
        self.service.quickmove = self.quickmove
        self.options_path = self.path.with_name("inventory-options.json")
        try:
            options = json.loads(self.options_path.read_text(encoding="utf-8"))
            shortcut = parse_binding(options.get("shortcut", "ctrl+shift+f6"))
            if shortcut and (shortcut.key.startswith("mouse") or not {"ctrl", "shift"}.issubset(shortcut.modifiers)):
                raise ValueError("Inventory shortcut must include Ctrl+Shift.")
            self.quickmove.shortcut = str(shortcut) if shortcut else ""
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError):
            warning = "Inventory shortcut settings ignored; using Ctrl+Shift+F6."
        self._mode_pending = False
        self.tray = None
        self._quick_dialog = None
        self._quick_status = None
        self._closed = False
        self._poll_id = None
        self._record_slot = None
        self._focus_token = (0, 0)
        self._detected = False
        self._poll_count = 0
        self._build(settings)
        try:
            self.service.start()
        except Exception:
            try:
                self.service.stop()
            finally:
                if self.instance:
                    self.instance.close()
            raise
        # Tray is optional if Windows shell is unavailable; window remains usable.
        if tray_factory is not None or api is None:
            from .tray import Tray
            self.tray = (tray_factory or Tray)(self.api, self.service.events, lambda: self.engine.enabled)
            try:
                self.tray.start()
            except (OSError, RuntimeError):
                self.tray = None
                warning = "System tray unavailable; minimize keeps the normal taskbar window."
        self.root.bind("<Unmap>", self._minimized)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll()
        self.updates.automatic(settings.auto_updates)
        if settings.indicator:
            self.show_indicator()
        if warning or calibration_warning:
            self.notice.set(warning or calibration_warning)

    def _build(self, settings):
        self.root.title(f"BloxBinds — {__version__} Beta")
        self.root.geometry("570x790")
        self.root.minsize(540, 780)
        self.root.configure(background="#f3f5f7")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f5f7")
        style.configure("TLabel", background="#f3f5f7", foreground="#172d3d", font=("Segoe UI", 10))
        style.configure("TButton", padding=(8, 2), font=("Segoe UI", 9))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Small.TLabel", font=("Segoe UI", 9), foreground="#435666")
        style.configure("TCheckbutton", background="#f3f5f7", font=("Segoe UI", 9))
        body = ttk.Frame(self.root, padding=20)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="BloxBinds", style="Title.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        self.connection = tk.StringVar(value="Roblox: checking…")
        ttk.Label(body, textvariable=self.connection).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))
        self.toggle = ttk.Button(body, text="Remapping: OFF — click to enable", command=self.toggle_enabled)
        self.toggle.grid(row=2, column=0, columnspan=4, sticky="ew")
        self.activity = tk.StringVar(value="Disabled")
        ttk.Label(body, textvariable=self.activity, style="Small.TLabel").grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 12))
        ttk.Label(body, text="Hotbar slot").grid(row=4, column=0, sticky="w")
        ttk.Label(body, text="Key / modifier combination / mouse").grid(row=4, column=1, sticky="w")
        self.bindings = []
        self.entries = []
        for slot, value in enumerate(settings.bindings, 1):
            row = 4 + slot
            ttk.Label(body, text=f"Slot {slot}  →  {slot}").grid(row=row, column=0, sticky="w", padx=(0, 12))
            variable = tk.StringVar(value=value)
            entry = ttk.Entry(body, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", pady=3, padx=(0, 8))
            ttk.Button(body, text="Record", command=lambda i=slot - 1: self.record(i)).grid(row=row, column=2, sticky="ew")
            ttk.Button(body, text="Clear", width=6, command=lambda i=slot - 1: self.clear_slot(i)).grid(row=row, column=3, padx=(5,0))
            self.bindings.append(variable)
            self.entries.append(entry)
        buttons = ttk.Frame(body)
        buttons.grid(row=14, column=0, columnspan=4, sticky="ew", pady=(10, 8))
        ttk.Button(buttons, text="Save & apply", command=self.save).pack(side="left")
        ttk.Button(buttons, text="Reset defaults", command=self.confirm_reset).pack(side="left", padx=8)
        ttk.Button(buttons, text="Quick-move…", command=self.open_quickmove).pack(side="left")
        self.quick_indicator = tk.StringVar(value="Quick-Move: Disabled")
        ttk.Label(body, textvariable=self.quick_indicator, style="Small.TLabel").grid(row=21, column=0, columnspan=4, sticky="w", pady=(6,0))
        self.notice = tk.StringVar(value="Starts OFF. Save edits, then enable remapping.")
        ttk.Label(body, textvariable=self.notice, wraplength=510, style="Small.TLabel").grid(row=15, column=0, columnspan=4, sticky="w", pady=(0, 10))
        ttk.Label(body, text="Hotbar compatibility (manual; separate from Quick-Move)").grid(row=16, column=0, columnspan=4, sticky="w")
        self.compatibility = tk.StringVar(value=settings.compatibility)
        combo = ttk.Combobox(body, textvariable=self.compatibility, values=COMPATIBILITIES, state="readonly")
        combo.grid(row=17, column=0, columnspan=4, sticky="ew", pady=(3, 4))
        combo.bind("<<ComboboxSelected>>", self.compatibility_changed)
        self.protect = tk.BooleanVar(value=settings.protect_text)
        ttk.Checkbutton(body, text="Protect chat/text entry (recommended)", variable=self.protect).grid(row=18, column=0, columnspan=4, sticky="w")
        self.automatic = tk.BooleanVar(value=settings.automatic_detection)
        ttk.Checkbutton(body, text="Automatic Roblox Detection (background status)", variable=self.automatic).grid(row=19, column=0, columnspan=4, sticky="w")
        ttk.Label(body, text=("Help: Record Ctrl/Shift/Alt + a key or Mouse3/Mouse4/Mouse5.\n"
                              "Detection OFF: enable manually; Roblox focus is always required.\n"
                              "Ctrl+Alt+F12 disables globally. F10 pauses/resumes in Roblox.\n"
                              "Enter and / pause until F10. Pause before clicking any text field.\n"
                              "Quick-move: experimental manual mode; use Quick-move… above.\n"
                              "Unknown allows testing; Verified by me is your current-game check.\n"
                              "Custom inventories and simulated input may be incompatible."),
                  style="Small.TLabel", wraplength=510).grid(row=20, column=0, columnspan=4, sticky="nw", pady=(12, 0))
        ttk.Button(body, text="Options & updates…", command=self.open_options).grid(row=22,column=0,columnspan=4,sticky="w",pady=(5,0))

    def open_options(self):
        if self._features_dialog and self._features_dialog.winfo_exists():
            self._features_dialog.lift()
            return
        dialog = self._features_dialog = tk.Toplevel(self.root)
        dialog.title("BloxBinds — Options & updates")
        frame = ttk.Frame(dialog,padding=16)
        frame.pack(fill="both",expand=True)
        self._feature_vars = {}
        for name, label in (("launch_with_windows","Launch with Windows (minimized; remapping starts OFF)"),
                            ("indicator","Show compact status indicator"),
                            ("indicator_topmost","Keep status indicator always on top"),
                            ("sound_feedback","Sound Feedback (Windows system volume)")):
            variable = tk.BooleanVar(value=getattr(self.engine.settings,name))
            self._feature_vars[name] = variable
            ttk.Checkbutton(frame,text=label,variable=variable,
                            command=lambda n=name,v=variable: self.set_preference(n,v.get())).pack(anchor="w")
        ttk.Label(frame,text="Extract to a permanent folder before enabling startup.\nDisable startup before moving or deleting BloxBinds.",style="Small.TLabel").pack(anchor="w",pady=(4,10))
        row = ttk.Frame(frame); row.pack(fill="x")
        ttk.Button(row,text="Export Settings",command=self.export_backup).pack(side="left")
        ttk.Button(row,text="Import Settings",command=self.import_backup).pack(side="left",padx=8)
        ttk.Separator(frame).pack(fill="x",pady=12)
        ttk.Label(frame,text=f"Updates — Current version: {__version__} Beta").pack(anchor="w")
        ttk.Label(frame,textvariable=self.update_status,wraplength=470,style="Small.TLabel").pack(anchor="w",pady=5)
        variable = tk.BooleanVar(value=self.engine.settings.auto_updates)
        self._feature_vars["auto_updates"] = variable
        ttk.Checkbutton(frame,text="Check once per session automatically (optional GitHub request)",variable=variable,
                        command=lambda: self.set_preference("auto_updates",variable.get())).pack(anchor="w")
        row = ttk.Frame(frame); row.pack(fill="x",pady=8)
        self._check_button = ttk.Button(row,text="Check for Updates",command=self.check_updates)
        self._check_button.pack(side="left")
        self._download_button = ttk.Button(row,text="Open Download Page",command=self.open_download,
                                           state="normal" if self._update_url else "disabled")
        self._download_button.pack(side="left",padx=8)
        def close():
            dialog.destroy()
            self._features_dialog = None
            self._feature_vars = {}
        dialog.protocol("WM_DELETE_WINDOW",close)
        ttk.Button(frame,text="Close",command=close).pack(anchor="e")

    def set_preference(self, name, value):
        old = self.engine.settings
        new = replace(old, **{name: value}).validate()
        registered = False
        try:
            if name == "launch_with_windows":
                self.startup.set(value)
                registered = True
            save_settings(self.path,new)
        except (ValueError,OSError) as error:
            if registered:
                try:
                    self.startup.set(old.launch_with_windows)
                except OSError:
                    self.notice.set("Startup rollback failed; inspect the Launch with Windows option before closing.")
            if name in self._feature_vars:
                self._feature_vars[name].set(getattr(old,name))
            messagebox.showerror("Could not save option",str(error),parent=self._features_dialog or self.root)
            return False
        with self.engine.lock:
            self.engine.settings = new  # Optional preferences never reset remapping/pause state.
        self.sounds.enabled = new.sound_feedback
        if name in {"indicator", "indicator_topmost"}:
            if new.indicator:
                self.show_indicator()
            elif self.indicator:
                self.indicator.hide()
        if name == "auto_updates" and self.updates.automatic(value):
            self.update_status.set("Checking GitHub…")
        self.notice.set("Option saved.")
        return True

    def show_indicator(self):
        try:
            if self.indicator is None:
                from .indicator import Indicator
                self.indicator = (self._indicator_factory or Indicator)(self.root,
                    lambda: self.set_preference("indicator",False),
                    lambda position: self.set_preference("indicator_position",position))
            self.indicator.show(self.activity.get(),self.engine.settings.indicator_position,
                                self.engine.settings.indicator_topmost)
        except (OSError,tk.TclError) as error:
            if self.indicator:
                self.indicator.close()
                self.indicator = None
            self.notice.set(f"Status indicator unavailable: {error}")

    def check_updates(self):
        if self.updates.check():
            self.update_status.set("Checking GitHub…")
            if self._features_dialog:
                self._check_button.configure(state="disabled")

    def open_download(self):
        if valid_release_url(self._update_url):
            import webbrowser
            webbrowser.open(self._update_url)

    def export_backup(self):
        path = filedialog.asksaveasfilename(parent=self.root,title="Export BloxBinds settings",
                    defaultextension=".json",initialfile="BloxBinds-settings.json",filetypes=[("JSON settings","*.json")])
        if not path:
            return
        try:
            if Path(path).resolve() in {p.resolve() for p in (self.path,self.calibration_path,self.options_path)}:
                raise ValueError("Choose a separate backup file; do not overwrite BloxBinds' local settings.")
            export_settings(Path(path),self.current_settings())
            self.notice.set("Portable settings exported. Startup and calibration are excluded.")
        except (ValueError,OSError) as error:
            messagebox.showerror("Export failed",str(error),parent=self.root)

    def import_backup(self):
        path = filedialog.askopenfilename(parent=self.root,title="Import BloxBinds settings",filetypes=[("JSON settings","*.json")])
        if not path:
            return
        try:
            settings = import_settings(Path(path),self.engine.settings)
            shortcut = parse_binding(self.quickmove.shortcut)
            if shortcut and shortcut in validate_bindings(settings.bindings):
                raise ValueError("A binding conflicts with the Inventory Mode shortcut.")
            if not messagebox.askyesno("Replace settings?","Replace current hotbar and portable preferences? Remapping will be OFF. Startup and calibration stay local.",parent=self.root):
                return
            save_settings(self.path,settings)  # Persist before changing any UI/runtime state.
        except (ValueError,TypeError,OSError) as error:
            messagebox.showerror("Import failed",str(error),parent=self.root)
            return
        self.cancel_recording()
        self._mode_pending = False
        self.quickmove.enable(False)
        self.engine.apply(settings)
        for variable,value in zip(self.bindings,settings.bindings): variable.set(value)
        self.compatibility.set(settings.compatibility)
        self.protect.set(settings.protect_text)
        self.automatic.set(settings.automatic_detection)
        for name,variable in self._feature_vars.items(): variable.set(getattr(settings,name))
        self.sounds.enabled = settings.sound_feedback
        if settings.indicator:
            self.show_indicator()
        elif self.indicator:
            self.indicator.hide()
        self.updates.automatic(settings.auto_updates)
        self.notice.set("Settings imported and saved. Remapping and Quick-Move are OFF.")

    def open_quickmove(self):
        self.cancel_recording()
        self.quickmove.cancel()
        self._mode_pending = False
        if self._quick_dialog and self._quick_dialog.winfo_exists():
            self._quick_dialog.lift()
            return
        dialog = self._quick_dialog = tk.Toplevel(self.root)
        dialog.title("Quick-Move — experimental manual Inventory Mode")
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        enabled = tk.BooleanVar(value=self.quickmove.enabled)
        ttk.Checkbutton(frame, text="Enable experimental Quick-Move this session",
                        variable=enabled, command=lambda: self.quickmove.enable(enabled.get())).pack(anchor="w")
        ttk.Label(frame, text=("Backpack/item detection is unavailable. You assert it is open by arming Inventory Mode.\n"
                               "Quick-Move has NOT been verified in the actual Roblox client.\n"
                               "Compatibility: choose Compatible only after your own built-in backpack drag test.\n"
                               "Unknown / Unsupported block Quick-Move; ordinary hotbar bindings remain separate."),
                  style="Small.TLabel").pack(anchor="w",pady=8)
        compatibility = tk.StringVar(value=self.quickmove.compatibility)
        combo = ttk.Combobox(frame,textvariable=compatibility,values=("Unknown","Compatible","Unsupported"),state="readonly")
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>",lambda _: self.quickmove.set_compatibility(compatibility.get()))
        ttk.Label(frame,text="Inventory Mode shortcut (Ctrl+Shift combination; blank disables shortcut)",style="Small.TLabel").pack(anchor="w",pady=(8,0))
        shortcut = tk.StringVar(value=self.quickmove.shortcut)
        ttk.Entry(frame,textvariable=shortcut).pack(fill="x")
        def save_shortcut():
            try:
                binding = parse_binding(shortcut.get())
                if binding and (binding.key.startswith("mouse") or not {"ctrl","shift"}.issubset(binding.modifiers)):
                    raise ValueError("Use a keyboard combination including Ctrl+Shift.")
                if binding and binding in self.engine.mapping:
                    raise ValueError("Inventory Mode shortcut conflicts with a hotbar binding.")
                normalized = str(binding) if binding else ""
                save_json(self.options_path,{"version":1,"shortcut":normalized})
                self.quickmove.shortcut = normalized
                shortcut.set(normalized)
                self.notice.set("Inventory Mode shortcut saved.")
            except (ValueError,OSError) as error:
                self.notice.set(str(error))
                messagebox.showerror("Inventory Mode shortcut",str(error),parent=dialog)
        ttk.Button(frame,text="Save shortcut",command=save_shortcut).pack(anchor="w",pady=4)
        ttk.Label(frame,text=("Calibration: CLICK grid top-left and bottom-right, then all nine slot centers.\n"
                              "Exclude search/chat from the grid. Setup clicks are swallowed, never simulated.\n"
                              "Then click clear space inside the grid to record the marked EMPTY slots.\n"
                              "Only mark visibly empty targets. Their exact appearance is checked before dragging.\n"
                              "After setup: enable remapping, open backpack, hover an item, toggle Inventory Mode,\n"
                              "then press existing slot bindings. No per-item confirmation.\n"
                              "Close backpack with its normal key; mode also stops on focus loss/chat/Escape/F10.\n"
                              "Position changes stop mode; size/DPI/layout changes require recalibration."),style="Small.TLabel").pack(anchor="w",pady=8)
        ttk.Label(frame,text="Currently EMPTY target slots (comma-separated; e.g. 8,9)",style="Small.TLabel").pack(anchor="w")
        empty = tk.StringVar(value=",".join(map(str, sorted(self.quickmove.empty_slots))))
        ttk.Entry(frame,textvariable=empty).pack(fill="x")
        def calibrate(refresh=False):
            try:
                slots = {int(v.strip()) for v in empty.get().split(",") if v.strip()}
                if not slots or not slots.issubset(set(range(1,10))):
                    raise ValueError("Mark at least one actually empty slot, numbered 1–9.")
                self.quickmove.empty_slots = slots
                self.begin_quick_calibration(refresh)
            except ValueError as error:
                self.notice.set(str(error))
                messagebox.showerror("Empty target slots",str(error),parent=dialog)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x",pady=6)
        ttk.Button(buttons,text="Recalibrate",command=calibrate).pack(side="left")
        ttk.Button(buttons,text="Refresh empty slots",command=lambda: calibrate(True)).pack(side="left",padx=8)
        ttk.Button(frame,text="Arm / disable Inventory Mode",command=self.arm_inventory).pack(anchor="w")
        self._quick_status = tk.StringVar(value=self.quickmove.status())
        ttk.Label(frame,textvariable=self._quick_status,wraplength=600).pack(anchor="w",pady=8)
        def close_panel():
            if self.quickmove.calibrating:
                self.quickmove.calibrating = False
                self.quickmove.profile = None
            dialog.destroy()
            self._quick_dialog = None
            self._quick_status = None
        dialog.protocol("WM_DELETE_WINDOW",close_panel)
        ttk.Button(frame,text="Close",command=close_panel).pack(anchor="e")

    def begin_quick_calibration(self, refresh=False):
        self.cancel_recording()
        self._mode_pending = False
        self.engine.enable(False)
        self.notice.set(self.quickmove.begin_calibration(refresh))
        if self._quick_status:
            self._quick_status.set(self.notice.get())

    def arm_inventory(self):
        if self.quickmove.active or self._mode_pending:
            self._mode_pending = False
            self.quickmove.cancel()
            self.notice.set("Inventory Mode OFF.")
        elif self.engine.enabled and self.quickmove.enabled:
            self._mode_pending = True
            self.notice.set("Inventory Mode explicitly armed ONCE: return to the open backpack, with no text entry.")
        else:
            self.notice.set("Enable Quick-Move and remapping before arming Inventory Mode.")

    def _minimized(self, event):
        if event.widget == self.root and self.root.state() == "iconic" and self.tray and self.tray.available:
            self.root.withdraw()

    def restore(self):
        self.root.deiconify()
        self.root.lift()

    def current_settings(self):
        parsed = validate_bindings([value.get() for value in self.bindings])
        return replace(self.engine.settings,bindings=tuple(str(b) if b else "" for b in parsed),
                       compatibility=self.compatibility.get(),protect_text=self.protect.get(),
                       automatic_detection=self.automatic.get()).validate()

    def clear_slot(self, slot):
        self.cancel_recording()
        self.engine.enable(False)
        self.quickmove.cancel()
        self._mode_pending = False
        self.bindings[slot].set("")
        self.notice.set(f"Slot {slot + 1} cleared. Save & apply to keep this change.")

    def set_recorded_binding(self, slot, binding):
        conflicts = []
        for index, variable in enumerate(self.bindings):
            if index == slot:
                continue
            try:
                if binding and parse_binding(variable.get()) == binding:
                    conflicts.append(index)
            except ValueError:
                pass
        if conflicts:
            slots = ", ".join(f"Slot {i + 1}" for i in conflicts)
            if not messagebox.askyesno("Replace existing assignment?",
                    f"{binding} is already assigned to {slots}. Replace it? The old assignment will be cleared.", parent=self.root):
                self.notice.set("Replacement cancelled; previous bindings preserved.")
                return
            for index in conflicts:
                self.bindings[index].set("")
        self.bindings[slot].set(str(binding) if binding else "")
        self.notice.set(f"Recorded slot {slot + 1}. Save & apply to use it.")

    def cancel_recording(self):
        self.service.record(False)
        self._record_slot = None

    def save(self):
        self.quickmove.cancel()
        self._mode_pending = False
        self.cancel_recording()
        self.engine.enable(False)
        try:
            settings = self.current_settings()
            save_settings(self.path, settings)
            self.engine.apply(settings)
            for variable, value in zip(self.bindings, settings.bindings):
                variable.set(value)
            self.notice.set("Saved and applied. Remapping is OFF; enable when ready.")
        except (ValueError, OSError) as error:
            self.notice.set(str(error))
            messagebox.showerror("Could not save", str(error), parent=self.root)

    def confirm_reset(self):
        if messagebox.askyesno("Reset hotbar defaults?","Reset hotbar bindings, text protection and detection? Optional feature preferences stay unchanged. Click Save & apply afterward to persist the reset.",parent=self.root):
            self.reset()

    def reset(self):
        self._mode_pending = False
        self.cancel_recording()
        # Reset hotbar defaults; explicit opt-in feature preferences stay unchanged.
        self.engine.apply(replace(self.engine.settings,bindings=Settings().bindings,
                                 compatibility="Unknown",protect_text=True,automatic_detection=True))
        self.quickmove.enable(False)
        for slot, variable in enumerate(self.bindings, 1):
            variable.set(str(slot))
        self.compatibility.set("Unknown")
        self.protect.set(True)
        self.automatic.set(True)
        self.notice.set("Defaults restored. Click Save & apply to save them.")

    def compatibility_changed(self, _event=None):
        self.cancel_recording()
        self.engine.apply(replace(self.engine.settings, compatibility=self.compatibility.get()))
        self.notice.set("Compatibility updated; remapping OFF. Save to keep this setting.")

    def toggle_enabled(self):
        self.cancel_recording()
        if self.engine.enabled:
            self.engine.enable(False)
            self.quickmove.cancel()
            self._mode_pending = False
            return
        try:
            if self.current_settings() != self.engine.settings:
                self.notice.set("Save & apply your edits before enabling remapping.")
                return
        except ValueError as error:
            self.notice.set(str(error))
            return
        if not self.service.healthy():
            self.engine.fail("Input service stopped; restart BloxBinds before enabling.")
            self.notice.set(self.engine.error)
            return
        if not self.engine.enable(True):
            self.notice.set("Unsupported inventory: remapping stays OFF. Change compatibility to test.")
        else:
            self.notice.set("Enabled. Remapping activates only while Roblox is focused.")
            self.sounds.play("enabled")

    def record(self, slot):
        self.quickmove.cancel()
        self._mode_pending = False
        self.engine.enable(False)
        self._record_slot = slot
        self.service.record(True)
        self.root.focus_force()
        self.notice.set(f"Slot {slot + 1}: hold Ctrl/Shift/Alt, then press a key or Mouse3/4/5. Escape cancels.")

    def _poll(self):
        if self._closed:
            return
        try:
            focus = self.api.focus()
            token = (focus.hwnd, focus.pid)
            if token != self._focus_token:
                # The hook thread may already have handled this same transition.
                if token != self.service._last_focus:
                    self.engine.focus_lost()
                    self.quickmove.cancel()
                self._focus_token = token
            if self.engine.settings.automatic_detection:
                if self._poll_count % 8 == 0:
                    self._detected = self.api.detected()
            else:
                self._detected = focus.roblox
            self._poll_count += 1
            self.connection.set("Roblox: focused" if focus.roblox else
                                "Roblox: detected, not focused" if self._detected else
                                "Roblox: not detected")
            while True:
                try:
                    kind, value = self.service.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "record":
                    slot = self._record_slot
                    self._record_slot = None
                    if slot is not None and value is not None:
                        try:
                            binding = parse_binding(value)
                            self.set_recorded_binding(slot, binding)
                        except ValueError as error:
                            self.notice.set(str(error))
                    else:
                        self.notice.set("Recording cancelled.")
                elif kind == "emergency":
                    self._mode_pending = False
                    self.quickmove.cancel()
                    self._record_slot = None
                    self.notice.set("Emergency stop: remapping OFF.")
                elif kind == "error":
                    self.notice.set(value)
                elif kind == "quickmove":
                    self.notice.set(value)
                    if self._quick_status:
                        self._quick_status.set(value)
                elif kind == "sound":
                    self.sounds.play(value)
                elif kind == "update":
                    from datetime import datetime
                    self.update_status.set(value.message + "\nLast checked: " + datetime.now().strftime("%Y-%m-%d %H:%M"))
                    self._update_url = value.url if valid_release_url(value.url) else None
                    if self._features_dialog:
                        self._check_button.configure(state="normal")
                        self._download_button.configure(state="normal" if self._update_url else "disabled")
                elif kind == "tray":
                    if value == "exit":
                        self.close()
                        return
                    if value == "restore":
                        self.restore()
                    elif value == "toggle":
                        self.toggle_enabled()
                    elif value == "indicator":
                        self.set_preference("indicator",True)
                elif kind == "calibrated":
                    profile, captured_geometry = value
                    try:
                        mouse = self.service.mouse_api()
                        if not focus.roblox or focus.text_control or mouse.geometry(focus) != captured_geometry:
                            raise OSError("Window/focus changed before empty-slot capture; refresh again.")
                        hashes = tuple(mouse.fingerprint(focus.hwnd,captured_geometry.absolute(point),profile.radius)
                                       if i+1 in self.quickmove.empty_slots else None
                                       for i,point in enumerate(profile.slots))
                        if self.api.focus() != focus or mouse.geometry(focus) != captured_geometry:
                            raise OSError("Focus/geometry changed during empty-slot capture.")
                        profile = replace(profile,empty_hashes=hashes).validate()
                        save_calibration(self.calibration_path,profile)
                        self.quickmove.profile = profile
                        self.quickmove.used.clear()
                        self.notice.set("Calibration and empty references saved. Re-enable remapping; arm Inventory Mode in Roblox.")
                    except (OSError,ValueError) as error:
                        self.quickmove.profile = replace(profile,empty_hashes=())
                        self.notice.set(f"Empty targets not verified: {error}")
            if self._mode_pending and focus.roblox:
                self._mode_pending = False
                try:
                    if focus.text_control or self.engine.text_paused or not self.engine.enabled:
                        raise ValueError("Close text entry and resume remapping before arming Inventory Mode.")
                    geometry,_ = self.service.mouse_api().snapshot(focus)
                    self.quickmove.activate(geometry)
                    with self.engine.lock:
                        self.engine.generation += 1
                except (OSError,ValueError) as error:
                    self.quickmove.cancel()
                    self.notice.set(str(error))
            current_geometry = None
            if self.quickmove.enabled and self.quickmove.profile and focus.roblox:
                try:
                    current_geometry = self.service.mouse_api().geometry(focus)
                    if self.quickmove.active and current_geometry != self.quickmove.geometry:
                        self.quickmove.cancel()
                except OSError:
                    self.quickmove.cancel()
            if not self.engine.enabled or not focus.roblox or focus.text_control or self.engine.text_paused:
                self.quickmove.cancel()
            self.toggle.configure(text="Remapping: ON — click to disable" if self.engine.enabled else
                                  "Remapping: OFF — click to enable")
            state = self.engine.status(focused=focus.roblox, detected=self._detected,
                                       native_text=focus.text_control, inventory=self.quickmove.active)
            self.activity.set(state)
            if self.tray:
                self.tray.set_status(state)
            if self.indicator:
                try:
                    self.indicator.set_status(state)
                    if self._poll_count % 32 == 0:
                        self.indicator.recover_position()
                except (OSError,tk.TclError):
                    self.indicator.close()
                    self.indicator = None
                    self.notice.set("Status indicator unavailable; remapping is unaffected.")
            quick_status = self.quickmove.status(focused=focus.roblox,remapping=self.engine.enabled,geometry=current_geometry)
            self.quick_indicator.set("Quick-Move: " + quick_status)
            if self._quick_status and not self.quickmove.calibrating:
                self._quick_status.set(quick_status)
        except Exception as error:
            self.engine.fail(f"Status check failed; remapping OFF. {error}")
            self.quickmove.cancel()
            self.notice.set(self.engine.error)
            self.activity.set(self.engine.status())
            if self.indicator:
                self.indicator.set_status(self.activity.get())
            if self.tray:
                self.tray.set_status(self.activity.get())
        self._poll_id = self.root.after(250, self._poll)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.updates.close()
        self.sounds.close()
        if self.indicator:
            self.indicator.close()
        if self._poll_id:
            self.root.after_cancel(self._poll_id)
        try:
            self.service.stop()
        finally:
            try:
                if self.tray:
                    self.tray.stop()
            finally:
                if self.instance:
                    self.instance.close()
                self.root.destroy()
