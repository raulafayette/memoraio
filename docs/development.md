# Development

Create an isolated Python 3.12 environment and install requirements-v2.lock.txt. For the full test suite also install requirements-licensing.lock.txt. Use temporary data roots; do not point tests at a personal catalog. UI tests use a separate browser profile.

Run `python -m unittest discover -s tests -v`, `python -m compileall -q memoria licensing`, `node --check memoria/static/app.js` and `python scripts/audit_public.py . --tracked`. Build the Mac shell with `python3 macos/build.py` on macOS.

State belongs in the catalog or explicit versioned manifests, not the chat. Keep original objects immutable. Test interrupted writes, leases and migrations where relevant. Never silently widen source scope, overwrite valid prior versions, turn missing fields into invented facts or treat generated text as original speech.

Review dependency changes with current upstream documentation and package license metadata. Keep model revisions fixed, inspect format/extractor support and preserve the previous installed runtime for rollback. No production keys are required for local development.
