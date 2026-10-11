# BloxBinds v1.3.0 Beta — Smart Remapping

- Automatic background Roblox detection option, ON by default, with safe focus-based suspension/recovery. Turning it OFF retains manual enabling and always requires Roblox focus.
- Exact Ctrl/Shift/Alt shortcuts, either modifier side, with deterministic plain/combo precedence and improved modifier cleanup.
- Optional Middle Mouse alongside Mouse4/5; unbound buttons retain normal behavior.
- Duplicate recording offers replace/cancel; saving ambiguous shortcuts is blocked with slot details. Added per-slot Clear buttons.
- Separate manual/chat pause reasons and clearer engine-driven window/tray status, including error recovery.
- Preserves the backquote fix, emergency stop, saved bindings, tray controls and experimental Inventory Mode.
- Built-in GitHub update checker with stable/beta version comparisons, official download-page links and optional once-per-session checking. Network checks default OFF; no automatic download or installation.
- Optional current-user Windows startup, minimized to the tray with remapping OFF. Disable it before moving/deleting the extracted app.
- Optional compact, draggable status indicator with saved position, always-on-top control and off-screen recovery; shares actual engine status without activating the window.
- Validated portable JSON settings export/import with replacement confirmation and atomic persistence. Startup registration and calibration stay local.
- Optional asynchronous Windows sound feedback for explicit enabling and F10 pause/resume. Focus switching and background status updates stay silent.

Install by extracting BloxBinds-Release-1.3.0-Windows-x64.zip and running BloxBinds.exe; no Python, installer, administrator privileges or Roblox Studio required. Remapping and Quick-Move start OFF. Exit the previous instance before normal launch.

Testing: the owner reports successful manual Roblox testing of the previous 1.3.0 build. This optional-feature expansion has automated/native Windows checks, but has not received new Roblox gameplay testing. Quick-Move is still experimental and unverified, OFF by default. Custom chat/search fields and inventory state cannot be reliably detected. Ctrl+Alt/AltGr and reserved shortcuts cannot be assigned. Simulated input may be rejected; the executable is unsigned. Actual Windows sign-in startup, audio volume and individual multi-monitor/fullscreen setups remain on the manual checklist. A deleted app cannot remove its startup entry; disable startup before deletion. The update checker inspects the newest 100 releases and needs network access only when requested/opted in. Upstream runtime build-path metadata is disclosed in PRIVACY_AUDIT.md; anonymity is not guaranteed.

Review TEST_RESULTS.md, the README checklist and SHA256SUMS.txt before manually publishing. This task creates no commits, tags, pushes or GitHub release. Public developer: wirru. License: unchanged MIT.
