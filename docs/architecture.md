# Architecture

The AppKit/WKWebView shell is a local client. The loopback HTTP service owns authenticated UI/API access. A launchd supervisor restarts acquisition, processing and web processes; SQLite holds leases, history, source schedules and job controls. Three acquisition and three transcription slots share persistent channel turns; a separate maintenance worker handles local publication.

Acquisition: canonical platform URLs, explicit source identities, streaming enumeration, per-method checkpoints, platform cooldown and scope quarantine. A video's uploader does not automatically expand a selected playlist into that author's channel.

Transcription: YouTube uses available captions and a caption extractor fallback. Optional Instagram ASR uses temporary audio on a configured Apple Silicon installation. Access restrictions stop network attempts. Source caption files and prior transcript objects remain immutable; new exports are derived revisions. Content hashes and manifests link artifacts. Missing metadata remains unknown.

Storage: data/catalog.sqlite3; content-addressed originals; immutable transcripts; versioned library grouped by platform/source/item; local models; temporary resumable files; catalog backups. External export destinations get a dedicated Memoraio Library subfolder. Changing the export destination does not relocate the catalog or source objects.

Knowledge: FTS and local E5 vectors, rank fusion, document grouping and nearby segments under a context budget. Oracles have source assignments, rules, strategy and revision files. Systematic queries freeze available transcripts and checkpoint each examined document. Local Qwen generation requires valid evidence IDs; original quotes are never overwritten by conclusions.

Licensing is a separate prototype module and database. It has no access to library files and is not a dependency of the personal engine. A real backend would own provider credentials, signatures, accounts and entitlement checks. This branch deliberately supports simulated charges only.
