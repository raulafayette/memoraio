# Contributing

Start with a reproducible issue and discuss scope before a large change. Use synthetic media and temporary catalogs. Never upload personal libraries, captions, cookies, tokens, database copies, screenshots with source titles, or payment data.

Use Python 3.12 on Apple Silicon, install the pinned runtime and optional licensing test dependencies, and run the documented tests. Keep acquisition, local processing, UI and licensing independently reviewable. Preserve stable IDs and immutable artifacts; migrations must back up, preserve data and have regression coverage.

Pull requests should explain the trigger, resulting behavior, validation and limits. UI changes need keyboard, light/dark, narrow-window and actual macOS checks. Do not add extractor options without checking current support. Never respond to 429 with proxy/IP rotation or bypass access controls.

Review for correctness, data preservation, security boundaries and compatibility. A green test suite is required but does not certify platform coverage, transcription quality or commercial legality. Contributors retain copyright and license original contributions under MIT; third-party code must retain its own license and provenance.

Release maintainers must follow docs/distribution.md. Only source and sanitized artifacts may enter a public release. Production payment changes require separate review and provider sandbox evidence.
