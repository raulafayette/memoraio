# Testing

The automated suite uses disposable catalogs, generated media and simulated providers. It checks leases, pause/cancel/retry, migration preservation, scope quarantine, interrupted transfers, origin/session checks, enriched exports, independent operations, local video-to-audio reuse, citation rejection, checkpointed textual research and simulated payment security.

Requirements: Python 3.12, FFmpeg/ffprobe and the runtime lock; cryptography from requirements-licensing.lock.txt for licensing tests. No model download is needed for unit tests; model-dependent metadata is supplied by installed package versions. Local HTTP tests need loopback permissions.

UI: install Playwright in a development-only Node environment, set TEST_BROWSER if using an existing Chromium executable, and run `python -m tests.run_ui`. The fixture starts its own server/catalog and cleans up. Do not reuse a personal browser profile.

Real-network and real-inference checks are opt-in, run separately and require permission for each source. Record durations, model revision, origin, segment counts, bytes transferred, coverage denominator and limitations. A green fixture does not establish current support for a platform or transcription completeness.

CI is prepared for macos-15 arm64 and builds an ad hoc signed native artifact. The public repository runs these checks on every push; inspect the Actions tab for the exact commit result. A separate Ubuntu job checks the Windows/WSL engine and packages the source preview. Local validation does not substitute for clean-machine install, minimum OS, VoiceOver/keyboard, Finder/Dock reopening, sleep behavior and Developer ID/notarization testing.

## Recurring workspace and download-manager checks

The current suite also covers persistent discovery baselines, initial versus later inventories, partial checks, metadata-only refresh while paused, transactional pause/resume races, selected/all collective starts and deduplicated summaries. Monthly archive tests cover timezone boundaries, copy dates, preservation of edited text and MP3/MP4 shortcuts without moving original media. A media-only query test ensures the download manager does not probe the transcription-only catalog.

`python -m tests.run_ui` runs both the workspace/manager journey and a separate responsive-control test. The latter deliberately delays a catalog snapshot, checks that pause is acknowledged without waiting for that snapshot, and verifies that a stale response cannot undo the pause. It also keeps Play disabled while interruption is still being confirmed.
