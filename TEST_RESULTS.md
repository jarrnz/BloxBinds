# Test results — BloxBinds 1.2.0

Tested locally on Windows 11 x64, Python 3.12.14, Tk 8.6 and PyInstaller 6.22.3.

- **86 automated tests passed, no local skips**, using `python -m unittest discover -s tests -q`.
- Existing hotbar regression tests cover all nine slots, keyboard/Mouse4/Mouse5 combinations, duplicate validation, JSON persistence, focus handling, injected-event filtering, repeat suppression, emergency disable and clean hook/output shutdown.
- Inventory tests cover explicit opt-in, Unknown/Unsupported refusal, manual mode toggling, backpack pause versus chat pause, all nine slot targets, custom bindings, unsafe-source refusal without gameplay fallback, focus loss without automatic reactivation, coordinate/DPI changes and cancelled queued actions.
- Calibration tests cover clicked points, relative monitor coordinates, saved/legacy/corrupt calibration, empty-target references, refresh without repeated position calibration, invalid geometry and partial-calibration refusal.
- Drag tests mock the Windows input boundary. They cover exact empty-appearance mismatch, sample failure, repeat suppression and attempted-target reservation, physical-button/modifier guards, virtual-desktop coordinates, cancellation and balanced mouse-up after failures. No Roblox mouse actions are sent by these tests.
- A live screen test samples only a temporary BloxBinds test window twelve times, checks stable hash-only capture and verifies GDI resource cleanup. No screenshots are retained.
- Tk tests cover the existing settings UI and tray Restore/Toggle/Exit dispatch, including cleanup on tray errors. Native source and executable smoke tests verify real hook/tray startup, nine visible slots, a 570×750 window without clipping, and all three service threads stopping. Remapping and Quick-Move remain OFF throughout.
- The **standalone Windows executable smoke test passed with exit 0**. The executable is unsigned and bundles Python; users do not need Python installed.
- Privacy inspection covers 33 allowlisted public files, 289 bundled Python code modules and unpacked executable members. Own version metadata uses wirru; code filenames are relative. No scanned local developer identifiers or workspace paths were found. **59 upstream runtime build-account directory references remain** and are disclosed in PRIVACY_AUDIT.md. Source/release archives exclude settings, Git metadata, caches, logs and prior artifacts.
- No Git commits existed during the audit. Local author name is wirru; the local email is deliberately empty until a real GitHub noreply address is configured. A tested local Git hook blocks author/committer identities without wirru plus a noreply address. No history was rewritten, no commit made and nothing published.
- A GitHub Actions workflow is prepared, but has not been executed remotely here. CI permits an unavailable interactive tray and skips live screen sampling; those checks passed locally.

**Actual Roblox Quick-Move has NOT been tested.** A Roblox process was detected, but no inventory actions were performed against it. Existing hotbar operation was previously manually verified by the project owner; that does not verify the new inventory behavior.

Manual Inventory Mode asserts that the backpack is open; calibration asserts the source grid and empty targets. There is no automatic item/backpack/occupied-slot detection or access to inventory state. Exact visual matching can refuse translucent, animated or obscured slots, and visual evidence cannot guarantee emptiness for transparent/custom icons. Occupied-slot swapping is not implemented. Same-size layout changes and Roblox custom text fields require the user's explicit checks. Disable Quick-Move if controlled client testing cannot establish reliable behavior.

No Roblox file modifications, process-memory access, injection or security bypasses are used. The privacy scan does not guarantee anonymity.
