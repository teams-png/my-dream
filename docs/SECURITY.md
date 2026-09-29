# Security and Privacy Baseline

- Tenant scope is derived only from authenticated membership in `ActiveCompanyMiddleware`.
- Object querysets use `for_company(request.company)` and cross-tenant objects resolve as 404.
- Production refuses weak/missing secrets and enables TLS redirect, secure cookies, HSTS, content-type sniff protection, same-origin referrer policy, and frame denial.
- Login endpoints are throttled and failed attempts are tracked without revealing whether an account exists.
- Financial writes go through atomic service functions and journal entries are append/reverse, never silently rewritten.
- Audit log deletion/change is disabled in Django admin. PostgreSQL deployment must apply the insert-only grant migration using a restricted application role.
- Uploaded identity documents must use private object storage, short-lived signed access, malware scanning, size/type validation, and an explicit retention policy. The current HR module stores document metadata only.
- Logs include request/user/company correlation identifiers but must not include credentials, tokens, identity document contents, or full payment details.
