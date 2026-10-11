# BloxBinds

A free, lightweight Windows 11 hotbar keybind manager for the official Roblox desktop client. Developed by **wirru**, under the MIT License. Runs alongside Roblox; no Studio or development tools required.

**1.2.0:** Preserves the existing hotbar system and adds experimental manual Inventory Mode, saved calibration, conservative empty-target checks, and native Windows tray controls. Hotbar remapping was previously manually tested by the project owner. **Quick-Move has not been verified in the actual Roblox client.** It is not universally compatible.

## Install

Download the Windows x64 ZIP, extract it, and run `BloxBinds.exe`. Python and administrator privileges are not required. Keep the included notices with redistributed binaries. The executable is unsigned; Windows may warn about an unfamiliar publisher. No automatic startup is installed.

## Hotbar bindings

1. Open BloxBinds. Remapping starts OFF.
2. Edit or Record slots 1–9. Examples: `r`, `ctrl+q`, `shift+mouse4`, `mouse5`. Ctrl/Shift combinations are supported; leave a slot blank to unbind it.
3. Click **Save & apply**, then enable remapping. Duplicate bindings are rejected. Settings are saved under `%LOCALAPPDATA%\BloxBinds`.
4. Roblox must be focused. Focus loss suspends normal remapping; it resumes when Roblox returns to focus.

**Emergency stop:** Ctrl+Alt+F12 disables remapping globally. **F10** pauses/resumes in Roblox. Enter, `/`, and the backpack backquote key pause until F10 or an explicit Inventory Mode activation for the backpack pause. Native Windows text controls also pause remapping when text protection is enabled. Roblox custom text widgets are not reliably detectable: pause before clicking chat, search, or other text fields.

The main window's hotbar compatibility setting is separate from Quick-Move compatibility. Setting *hotbar* compatibility to Unsupported disables hotbar remapping. Leaving Quick-Move compatibility Unknown or Unsupported does not disable ordinary hotbar bindings.

## Quick-Move: experimental, manual only

There is no reliable automatic backpack, item, or occupied-slot detection here. Inventory Mode is **your explicit assertion that the built-in backpack is open and that you are hovering an item**. The app never reads Roblox inventory state. Do not use this with custom inventories or text entry.

First, test ordinary dragging yourself in the current game: open its built-in backpack, drag an expendable inventory item into an **empty** numbered hotbar slot, and verify the destination. If this fails, choose Unsupported in the Quick-Move panel and leave Quick-Move off. Choose **Compatible** only after your own successful check. Compatible means user-verified support for the current session, not automatic detection or a developer-tested claim. Unknown and Unsupported block Quick-Move. Compatibility resets to Unknown on each launch; change it when switching games.

### Calibrate once

1. Open **Quick-move…**, enable experimental Quick-Move, and list only visibly **EMPTY target slots**, such as `8,9`. Never mark occupied slots empty.
2. Click **Recalibrate**. Remapping is disabled during setup. Open the built-in backpack and keep its layout and window geometry stable.
3. Click the item grid's top-left, then bottom-right; exclude the search box, chat, and hotbar. Click all nine hotbar slot centers in order. These setup clicks are intercepted; calibration never simulates mouse input.
4. Click clear space inside the grid, away from all hotbar slots. The app records hashes of the marked empty targets' visible appearance. No screenshots are saved.
5. Calibration is saved locally and reused across sessions. Resize/DPI/layout changes require recalibration. Window movement disables active mode; relative coordinates can be reused at the same size/DPI after explicitly rearming.

Existing 1.1 calibration retains its positions; use **Refresh empty slots** to add the new empty-target references. This needs only the final grid click, not eleven new position clicks. A cancelled partial recalibration cannot reuse uncertain targets.

### Move an item

1. Close the panel and enable hotbar remapping. Open the built-in backpack and hover an item inside the calibrated grid.
2. Toggle Inventory Mode with **Ctrl+Shift+F6** (change or disable this shortcut in the panel). It must not conflict with a hotbar binding. Alternatively, the panel's **Arm / disable Inventory Mode** button arms it once when you explicitly return to Roblox; it never rearms after a later focus loss.
3. Press the existing binding for an empty target slot. For example, hover a sword and press `r` if slot 9 is bound to `r`. Release combination modifiers promptly. There is **no per-item confirmation or confirmation timer**.
4. The app attempts an ordinary left-button drag only while focused, mode is active, text is not paused, coordinates are valid, the cursor is inside the calibrated grid, and the target's visible patch exactly matches its empty reference. Slot bindings are consumed without gameplay fallback when mode is active but a move is unsafe.
5. Each attempted target is reserved until **Refresh empty slots**: first manually empty/check the targets, update the empty list, then capture their appearance. Occupied-slot swaps/overwrites are not supported. Multiple different verified empty slots need no per-item setup.

Backquote, Escape, chat keys, F10, clicking, scrolling, focus loss, or conflicting input stop Inventory Mode. Moving the physical mouse cancels an in-flight drag. Returning focus never automatically rearms it. Closing inventory with a game-specific click/control may not be detectable; turn mode off explicitly before returning to gameplay. Emergency stop always remains available. A started drag is balanced with a mouse-button release even if it is cancelled; the cursor is not automatically restored.

## Limitations and troubleshooting

- Simulated keyboard/mouse input may be rejected or behave differently in any game. This app cannot verify a submitted drag's result. Actual Quick-Move client testing is still required.
- Empty references are visual evidence, not proof of inventory state. Transparent/custom icons, wrong calibration, mislabelled occupied targets, or game-specific layouts can defeat visual assumptions. Use only manually verified built-in backpack layouts, visibly empty targets, and expendable items. No automatic occupied-slot overwrite is implemented.
- Exact appearance matching intentionally refuses changed targets. Translucent backgrounds, camera motion, lighting, animation, tooltips, hover effects, UI scaling, and overlays can cause refusals. Refresh only when targets are actually empty; do not label occupied slots empty to bypass a refusal.
- The calibrated grid verifies coordinates, not whether its cursor point contains an item. Hovering blank space can attempt an empty drag while in manual mode. If reliable operation cannot be established in your game, disable Quick-Move and retain ordinary hotbar remapping.
- **Needs Calibration:** finish setup or refresh empty references; restore calibrated window size/DPI or recalibrate. **Compatibility Unknown / Unsupported:** Quick-Move stays blocked. **Roblox Not Focused:** return to the client, then explicitly rearm Inventory Mode.
- Text protection is a heuristic. F10 pause is the reliable user control before typing in Roblox's custom chat/search widgets.
- Minimize to the system tray. Left-click the tray icon to restore; right-click for Restore, Enable/Disable keybinds, or Exit. Closing the main window exits and releases hooks. If the Windows shell is unavailable, ordinary taskbar minimize is retained. No background service is installed.

## Privacy and safety

No accounts, credentials, analytics, network calls, cloud sync, automatic startup, process-memory inspection, injection, Roblox file changes, or security bypasses. Only window/process executable metadata, input hooks, ordinary simulated input, and small visible target patches are used. Screen patches stay in memory; only SHA-256 hashes and local calibration coordinates persist. Remapping and Quick-Move start OFF. Settings and screen hashes are excluded from the source/release bundles.

See [PRIVACY_AUDIT.md](PRIVACY_AUDIT.md) for the inspected release scope and remaining publication checks. BloxBinds developer metadata uses only wirru. Bundled runtime libraries retain upstream build-path metadata described in the audit; anonymity is not guaranteed. Keep a real GitHub-provided noreply address in your local Git configuration before public commits. No repository or release is published automatically.

## Build and test from source

Use Windows 11 x64 and Python 3.12 with Tkinter:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe main.py --smoke-test
.\.venv\Scripts\python.exe scripts/build.py
.\.venv\Scripts\python.exe scripts/audit_release.py --exe dist/BloxBinds.exe
.\.venv\Scripts\python.exe scripts/package_release.py
```

`requirements.txt` has no runtime pip dependencies: Tkinter and Windows ctypes are provided by Python. The safe smoke test checks native hooks, tray and clean shutdown while remapping remains OFF; close any other BloxBinds instance first. Build output is `dist/BloxBinds.exe` and includes Python, so end users do not install it. GitHub Actions builds/tests on Windows and uploads release bundles without publishing. Its smoke test allows an unavailable Windows shell; live screen sampling is skipped in CI. Local interactive tests check the real tray and sampling. Build logs, caches, local settings and previous artifacts are not part of public bundles.

## License

Copyright (c) 2026 wirru. BloxBinds source is licensed under the full [MIT License](LICENSE). Bundled runtimes retain their upstream license notices.
