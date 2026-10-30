# Distribution and maintenance

Build source from a reviewed commit on macOS with Apple's SDK. The result contains the native shell and original icon, not Python, FFmpeg, Node, models or personal data. Build tooling records explicit versions; byte-for-byte reproducibility across SDK updates is not claimed.

Before a binary release: choose a supported minimum macOS version; test an empty installation; audit every bundled wheel, library, executable and model; retain notices and required corresponding source; sign with a valid Developer ID; notarize and staple using Apple's current tools; verify Gatekeeper and install/uninstall on a clean Mac. Ad hoc signatures are local development signatures only. Do not strip quarantine or disable privacy protections to pass a test.

Upgrades are manual. Pause tasks, back up the catalog, verify original hashes, retain previous source/runtime and test migrations on a copied catalog. Replace code/runtime only after validation. The personal installation uses a permanent engine/runtime/data folder outside the checkout; reinstall the launch agent only if those installed paths change. Rollback may use the saved catalog and prior runtime; don't overwrite a newer database without preserving it first.

The daily automatic backup covers the catalog only. A full backup must separately copy originals, transcript versions, library/manifests and configuration/models as needed, verify hashes and be restored in a separate test directory. A backup on the same disk is not disaster protection.

To uninstall, use `python scripts/uninstall_service.py` to stop/remove this project's launch agent while preserving all data. Remove the app/source/runtime manually only after locating and copying any library you want to keep. No uninstall command in this project deletes the catalog or media.

The app distinguishes closing the window, hiding, exiting its interface while retaining tasks, pausing/interruption and exiting the service completely. Launchd starts after user login. Automatic sleep prevention is opt-in, active only for running tasks and released on pause/idle/exit. Sleep, logout and shutdown interrupt work; checkpoints permit later recovery.
