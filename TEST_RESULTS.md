# Test results — BloxBinds 1.2.1

Tested locally on Windows 11 x64, Python 3.12.14, Tk 8.6 and PyInstaller 6.22.3.

- **96 automated tests passed, zero failures or skips** in the full suite, run once with `python -m unittest discover -s tests -q`.
- Focused checks passed first: 26 core, 41 inventory and 12 UI tests. One new test initially asserted that the guarded drag method was never called; it was corrected to check that the stale job's guard actually refuses the action, then the inventory checks passed.
- Ten added regressions cover backquote pass-through/repeat handling, stale output cancellation, deliberate F10 and chat pauses, detected text controls, focus loss/return, Inventory Mode shortcut/button interactions, and a pause arriving during activation.
- Existing coverage preserves all nine bindings, Mouse4/Mouse5, modifiers, duplicate rejection, JSON settings/calibration, synthetic-event filtering, emergency disable, safe drag guards, native focus handling and tray/hook cleanup. Mouse input is mocked in inventory/drag tests; no Roblox mouse actions are sent.
- The live screen test samples only its own temporary test window and checks GDI cleanup; no screenshots are retained.
- An **isolated native source smoke test passed** with nine visible slots, native input hooks, real tray startup and clean shutdown of all three service threads. Remapping and Quick-Move stayed OFF. The ordinary source smoke command was blocked by an already-running BloxBinds instance. The rebuilt executable smoke attempt also exited 1 while that instance remained running; its independent startup/shutdown check is therefore still outstanding. The existing app was not stopped.
- **The v1.2.1 Windows executable rebuilt successfully.** Windows version metadata identifies 1.2.1 and wirru. End users do not need Python; the executable remains unsigned.
- Privacy inspection passed for 33 public files and 289 bundled code modules: no scanned local developer identifiers or workspace paths, and relative bundled Python filenames. The existing 59 upstream runtime account-directory references remain disclosed in PRIVACY_AUDIT.md; anonymity is not guaranteed.
- The configured wirru / GitHub noreply commit identity and MIT License text are unchanged. No Git identity changes, commits, pushes, tags, history rewrites or publication were performed. Release archives exclude Git metadata, settings, caches and build logs. The Windows workflow's artifact names now use 1.2.1; it was not run remotely here.

## Fix and limits

Backquote previously shared the sticky chat-pause branch: every press set the pause, including the press that closed the backpack. It now passes through, invalidates queued output and cancels Inventory Mode without changing a pause. F10 remains the independent manual pause/resume control. Enter and slash still pause until F10; native text protection remains in place. Inventory Mode can no longer clear a deliberate manual/chat pause.

No open/closed backpack state is inferred. Roblox custom chat/search widgets are not reliably detectable; pause with F10 before clicking them. Quick-Move remains experimental, OFF by default and manually armed. It has **not been tested in the actual Roblox client** during this update. Existing owner-verified hotbar behavior does not verify Quick-Move or this client-side fix.

Before client testing, exit the existing BloxBinds instance and start v1.2.1. Enable a custom binding, open and close the backpack using backquote, and verify that the binding works without F10. Repeat after an explicit F10 pause: backquote and focus changes must leave it paused until F10. Check chat/search protection with disposable inputs. Keep Quick-Move OFF for these checks. If testing Quick-Move separately, follow the README's controlled empty-slot calibration and manual compatibility checks with expendable items.

The remaining executable smoke check is: close the other instance, then run `BloxBinds.exe --smoke-test` in Windows. No further build is needed for that check.
