# BloxBinds

A free, lightweight Windows 11 hotbar keybind manager for the official Roblox desktop client. Developed by **wirru**, under the MIT License. Runs alongside Roblox; no Studio or development tools required.

**1.3.0 Beta — Smart Remapping:** automatic background detection, exact Ctrl/Shift/Alt shortcuts, optional Middle Mouse, conflict replacement, per-slot Clear, and shared window/tray status. Now includes optional GitHub update checking, Windows startup, a compact status indicator, portable settings backups, and sound feedback. The owner reports successful automated and manual Roblox testing of the previous 1.3.0 build. **This feature expansion has not been gameplay-tested in Roblox; Quick-Move remains unverified and experimental.**

## Install

Download `BloxBinds-Release-1.3.0-Windows-x64.zip`, extract it, and run `BloxBinds.exe`. Python and administrator privileges are not required. Keep the included notices with redistributed binaries. The executable is unsigned; Windows may warn about an unfamiliar publisher. No automatic startup is installed.

## Optional features

Open **Options & updates…**. Each option is saved immediately, without resetting remapping or manual/chat pauses. Network checking, launch with Windows, the status indicator, and sounds are OFF by default, including when upgrading older settings.

- **Updates:** click **Check for Updates**, or enable one automatic check per session. The app requests public release metadata from the official `jarrnz/BloxBinds` GitHub API in a background thread. It checks the newest 100 published releases and compares semantic versions, including beta releases; a stable 1.3.0 release ranks above 1.3.0 Beta. Invalid versions/URLs and drafts are ignored. A valid newer release enables **Open Download Page** in your browser. No update is downloaded, installed, or executed. Offline, timeout, rate-limit and unavailable-release messages leave the app usable. Only a generic app User-Agent is sent; no credentials or settings. GitHub can still see the request's IP address and ordinary HTTP metadata. API redirects are refused.
- **Launch with Windows:** extract to a permanent folder first. Enabling this registers only BloxBinds in the current user's Windows Run key. Sign-in starts it minimized to the tray with remapping OFF. If the tray is unavailable, the main window stays usable. Single-instance protection still applies. Disable startup **before moving or deleting the app**. Launching it manually from a moved location repairs a previously enabled entry. A deleted app cannot clean its own registry entry: remove BloxBinds from Windows Startup Apps/the current-user Run key if you forgot to disable it. Running directly inside an unextracted ZIP or a temporary download folder is unsuitable for startup.
- **Compact status:** toggle the indicator or choose **Show status indicator** from the tray. It shows the engine's actual status, including manual/chat/error states. Drag its title to move; × hides it. Position is saved locally, with optional always-on-top. It uses Windows non-activation styles and does not grab keyboard focus. Place it away from gameplay controls: the small window accepts clicks for dragging/hiding. It checks monitor work areas when shown/moved and about every eight seconds while visible, recovering from disconnected monitors or off-screen saved coordinates. There is no separate polling loop. Exclusive fullscreen may hide the indicator; use windowed/borderless mode if needed.
- **Settings backup:** **Export Settings** writes a versioned, portable JSON backup of hotbar bindings and safe preferences, including detection, updates, indicator visibility/topmost and sound. **Import Settings** validates it and asks before replacing settings. Malformed JSON, duplicate/reserved shortcuts, unsupported schemas and unexpected fields are rejected before saving. A successful import starts remapping and Quick-Move OFF; existing manual/chat pauses still require their normal explicit clearance. Startup registration, monitor position, calibration, Inventory Mode shortcut, runtime enable/pause states and game verification are excluded. They remain local; compatibility becomes Unknown. Export includes current visible hotbar edits after validation. Local settings are not changed if validation, confirmation or persistence fails. **Reset defaults** resets the hotbar/text/detection controls; optional feature preferences stay unchanged until explicitly changed.
- **Sound Feedback:** short Windows system sounds for explicit enabling and F10 pause/resume, played asynchronously. No sounds for focus changes, polling, updates, indicator changes or startup. Loudness follows your Windows system-sound volume; audio availability and duration depend on the Windows sound scheme. No audio files or dependencies are added.

## Hotbar bindings

1. Open BloxBinds. Remapping starts OFF.
2. Edit or Record slots 1–9. Examples: `r`, `shift+r`, `ctrl+q`, `alt+e`, `ctrl+shift+r`, `shift+mouse4`, `ctrl+mouse5`, `alt+middle mouse`. Ctrl/Shift/Alt are supported; leave a slot blank or click **Clear** to unbind it. Middle Mouse (`mouse3`) is optional: it keeps its normal camera behavior until explicitly assigned.
3. Click **Save & apply**, then enable remapping. Duplicate bindings show the conflicting slots and block saving. When recording a duplicate, choose **Yes** to replace its old assignment or **No** to preserve both previous bindings. Settings are saved under `%LOCALAPPDATA%\BloxBinds`.
4. Roblox must be focused. Focus loss suspends normal remapping; it resumes when Roblox returns to focus, including after minimize/restore or a client restart, unless a manual/chat pause remains.

**Automatic Roblox Detection** defaults ON and checks for the desktop game client's visible windows about every two seconds; minimized windows count as visible. Foreground checks always guard input. Roblox Studio, browsers and other process names are excluded. Recognition uses the existing desktop executable names, not cryptographic publisher verification. Turning detection OFF skips background enumeration and keeps manual **Enable/Disable** activation with the same Roblox focus safety check. It never allows global remapping. Automatic detection does not turn remapping ON at startup; the app still starts OFF. Existing configuration values and bindings are retained; older files lacking this preference inherit ON, matching their previous automatic focus behavior. Settings are not rewritten during loading.

Shortcuts match the complete combination: `r` and `shift+r` select separate slots, without a plain-key fallback. Modifier order is normalized to Ctrl, Shift, Alt. Either left or right modifier works; sides share one binding. Hold modifiers, then press the final key/button when recording. Escape cancels and keeps the old binding. Recording disables remapping and shows the full shortcut before Save & apply. A held key/button creates only one hotbar command; release it before pressing again.

Windows-key shortcuts, Alt+Tab/Alt+F4/Alt+Space, Escape combinations, F10/F12 and chat/backpack controls cannot be assigned. Ctrl+Alt combinations are intentionally unsupported to preserve AltGr typing and system controls; Ctrl+Alt+F12 remains the global emergency stop. AltGr is not a supported Alt binding. No mouse wheel remapping is provided. Vendor mouse software that injects button events may be ignored; use native button events. Simulated modifier release/restore is tagged and balanced; rapid physical transitions and game-specific input handling still require client testing.

**Emergency stop:** Ctrl+Alt+F12 disables remapping globally. **F10** explicitly pauses/resumes in Roblox. Manual and chat pauses have independent reasons; focus, detection, enabling remapping and Inventory Mode never clear either. An explicit F10 resume clears both paused reasons. Enter and `/` pause until F10. Backquote opens/closes the backpack normally and cancels Inventory Mode without creating or clearing a pause. Ordinary hotbar remapping stays available whenever Roblox is focused, no F10/chat pause is active, and no protected text control is detected; closing the backpack needs no F10. BloxBinds does not infer whether the backpack is open. Inventory Mode cannot override a deliberate F10 or chat pause. Native Windows text controls also pause remapping when text protection is enabled. Roblox custom text widgets are not reliably detectable: pause before clicking chat, search, or other text fields.

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
- Text protection is a heuristic. Manual/chat pauses are shown separately, and a detected native text control shows Text Entry Paused. F10 pause is the reliable user control before typing in Roblox's custom chat/search widgets.
- Minimize to the system tray. Its tooltip and menu use the same engine status as the window: Active, Waiting, Not Focused, Manually Paused, Chat Paused, experimental Inventory Mode, Disabled, or Error / Recovery Needed. For an input error, fix the cause and explicitly re-enable or Save & apply; a focus change cannot silently recover it. If the input service has stopped, restart BloxBinds instead of re-enabling. Keep both applications at normal user privileges if Windows rejects input; do not disable Windows security. Left-click the tray icon to restore; right-click for Restore, Enable/Disable keybinds, or Exit. Closing the main window exits and releases hooks. If the Windows shell is unavailable, ordinary taskbar minimize is retained. No background service is installed.

## Privacy and safety

No accounts, credentials, analytics, cloud sync, process-memory inspection, injection, Roblox file changes, or security bypasses. The optional update checker makes only a public GitHub release-metadata request; network access is OFF by default. Only explicitly enabling startup creates a visible, reversible current-user Run entry. Window/process executable metadata, input hooks, ordinary simulated input, and small visible target patches are used. Screen patches stay in memory; only SHA-256 hashes and local calibration coordinates persist. Remapping and Quick-Move start OFF. Settings, backups and screen hashes are excluded from release bundles.

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

`requirements.txt` has no runtime pip dependencies: Tkinter and Windows ctypes are provided by Python. The safe smoke test checks native hooks, tray, layout and clean shutdown while remapping cannot be enabled. Close another BloxBinds instance first, or add `--isolated-smoke-test` to use an independent temporary test instance; normal startup still enforces one instance. `scripts/verify_input.py` checks modifier output only in its own foreground Tk window and safely skips if Windows denies focus. It does not test physical hardware capture or Roblox gameplay. Build output is `dist/BloxBinds.exe` and includes Python, so end users do not install it. GitHub Actions builds/tests on Windows and uploads release bundles without publishing. Its smoke test allows an unavailable Windows shell; live screen sampling is skipped in CI. Local interactive tests check the real tray and sampling. Build logs, caches, local settings and previous artifacts are not part of public bundles.

## Manual Roblox checklist for 1.3.0 Beta

Keep Quick-Move OFF for these checks:

1. Save distinct `r`, `shift+r`, `ctrl+q`, `alt+e`, `ctrl+shift+r`, Mouse4/5 and optional Middle Mouse bindings. Verify each selects only its intended slot, with one action per press.
2. Check unassigned Middle Mouse retains camera behavior. Try left/right modifiers; release them and verify ordinary typing has no stuck Ctrl/Shift/Alt state. Test on expendable items in a game where hotbar selection is harmless.
3. Alt+Tab away, minimize/restore, move between monitors, close and relaunch Roblox. Bindings must affect only the focused game client, with automatic recovery when safe. Confirm Studio/browser input is untouched.
4. F10-pause, switch away/back, and open/close the backpack with backquote. It must remain paused until F10. Without a prior pause, opening/closing with backquote must not require F10. Enter/slash chat pause must survive focus and Inventory Mode attempts; explicitly resume with F10 only after leaving text entry.
5. Record a duplicate, cancel, then replace it. Test Escape cancellation, reserved-key rejection, Clear, saving and restarting. Toggle background detection OFF: manual enabling still requires Roblox focus. Emergency-stop and tray Restore/Toggle/Exit must work.
6. Quick-Move is a separate optional experiment: follow the empty-slot calibration and compatibility checks above; no occupied-slot swaps or automatic backpack detection are supported.
7. Turn on the indicator while Roblox is focused; show/hide it from the tray, drag it and restart. Confirm showing it leaves gameplay focused, pause states agree with the main window/tray, and disconnected-monitor recovery is visible. Try your actual monitor/DPI/fullscreen setup.
8. Enable sound, explicitly enable remapping and F10 pause/resume; verify one sound each and silence during focus switching. Disable sounds and check your Windows volume/scheme.
9. Export settings, alter a binding and import with confirmation. Cancel another import and verify nothing changes. Check updates online/offline and confirm the browser opens only the official release page.
10. In a permanent extracted folder, enable startup, sign out/in and confirm one tray instance with remapping OFF. Disable it and confirm the entry is removed. Startup tests in automation use a mocked registry and do not change your actual startup settings.

## License

Copyright (c) 2026 wirru. BloxBinds source is licensed under the full [MIT License](LICENSE). Bundled runtimes retain their upstream license notices.
