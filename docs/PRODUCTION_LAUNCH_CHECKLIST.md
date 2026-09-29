# BookPilot Production Launch Checklist

Complete this checklist for every live environment and for each first client.
Items requiring credentials, hardware, legal review, or a real client cannot be
completed inside the source package.

## Platform deployment

- [ ] Create a strong unique `DJANGO_SECRET_KEY` and use the same value for web,
  worker and beat services.
- [ ] Create and securely retain a separate
  `PAYMENT_CREDENTIALS_ENCRYPTION_KEY`; changing or losing it makes saved
  gateway credentials unreadable.
- [ ] Configure the production domain in `DJANGO_ALLOWED_HOSTS` and
  `CSRF_TRUSTED_ORIGINS`; verify HTTPS redirect and certificate renewal.
- [ ] Provision PostgreSQL and Redis; deploy web, Celery worker and Celery beat.
- [ ] Configure a private S3-compatible bucket, enable versioning, and verify an
  uploaded logo survives a web-service restart.
- [ ] Configure SMTP and confirm a real notification reaches a test mailbox.
- [ ] Configure Sentry (or equivalent) and verify a test error is captured
  without customer personal data.
- [ ] Configure automated encrypted database/media backups and complete a
  restore drill using `docs/OPERATIONS_RUNBOOK.md`.
- [ ] Run `python manage.py check --deploy`, migrations, seed command, full
  SQLite tests and PostgreSQL CI tests against the release commit.
- [ ] Verify `/health/` and `/ready/`, worker readiness and beat task execution.

## Payments and subscriptions

- [ ] Open **Platform Setup -> Payment Gateways**, add only the providers the
  operator will use, save test keys first, and switch off test mode only after
  end-to-end verification.
- [ ] Verify webhook signatures, successful payment, failed payment, duplicate
  webhook idempotency and subscription renewal/expiry behaviour.
- [ ] Verify the manual bank-transfer approval flow when used.

## Client acceptance test

- [ ] Create a fresh tenant and complete profile, branch, tax, chart of accounts,
  opening balances, roles and module assignment.
- [ ] Run product/service -> purchase/stock -> barcode/POS sale -> payment ->
  return -> expense -> profit and stock reports.
- [ ] Verify tenant isolation using two real test tenants and restricted staff roles.
- [ ] Test barcode scanner, label printer and receipt/PDF printer on the client's
  actual devices and browser.
- [ ] Test mobile and desktop layouts, slow connection, CSV import/export and
  report totals against manual calculations.
- [ ] Confirm low-stock, overdue document, batch-expiry and subscription alerts.
- [ ] Obtain written approval for invoice layout, currency, tax treatment,
  privacy/retention policy and commercial terms from qualified local reviewers.

## Business-specific acceptance

- [ ] Boutique: size/colour/material/design variants, sets and returns.
- [ ] Mobile shop: IMEI/serial intake and sale, warranty, repair, trade-in and
  instalment collection.
- [ ] Service clients: appointment/case/work order, package sale and billing.
- [ ] Gym: enrollment, renewal, freeze/unfreeze, attendance and invoice.
- [ ] Medical/clinic use: access rules, consent, retention and sensitive-record
  handling must pass a dedicated privacy/compliance review before live use.
