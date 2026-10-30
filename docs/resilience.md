# Resilience and validation

Explicit channel sessions persist scope, discovery, planning and per-item job associations in SQLite. Planning and job association are transactional; repeated clicks and recovered planning reuse existing work. File presence and checksums determine completed status. Failed or incomplete files are not represented as completed downloads.

Publication uses unique temporary files, atomic replacement and synchronization of files/directories. SQLite uses DELETE journaling, synchronous FULL and fullfsync on macOS. Leases, inherited staging locks and validated reuse support resuming interrupted operations. An explicitly started batch may recover after reopening the app; no periodic acquisition schedule is created.

The automated suite tests separate channels, scope selection, duplicate clicks, pause/resume/cancel, restart after discovery, expired leases, altered files, abrupt exit during an uncommitted SQLite transaction, simultaneous file writes, disk-full preservation, real HTTP interruption/Range resumption, and real FFmpeg conversion. UI validation uses an isolated library. YouTube enumeration responses in these tests are controlled fixtures.

These checks do not establish universal fault tolerance or permanent YouTube availability. Hardware failure, storage loss, platform changes and inaccessible media remain possible. Maintain an independent media backup when preservation is required.
