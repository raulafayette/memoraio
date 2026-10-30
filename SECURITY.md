# Security

The local interface binds to loopback and uses a per-session token, HttpOnly cookie, Host/Origin checks and a restrictive CSP. These controls do not replace operating-system account security. Do not expose the service to a network or port-forward it.

Do not put vulnerabilities, library excerpts, signed media URLs, tokens or payment data in public issues. Use GitHub private vulnerability reporting after it is enabled by the repository owner. Until then, request a private contact channel from a maintainer without posting exploit details or secrets.

The current branch is the supported development version. There is no promised response SLA. Keep dependencies pinned, review updates and test migrations in a disposable catalog before upgrading an installation. No automatic remote code download or self-update runs in the application.

Licensing is an isolated sandbox prototype. A source release must never include its database, private signing key, webhook secrets, account tokens or real charge records. Do not activate production payments from this branch.
