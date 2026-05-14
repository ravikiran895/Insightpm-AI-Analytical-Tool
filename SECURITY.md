# Security

InsightPM's security model is "single-tenant local tool, trusted operator." This document explains what that means in practice, what's protected, and how to report security issues.

---

## Threat model

**What we defend against:**

- **Accidental exposure** of your localhost / LAN instance to someone on the same network.
- **SQL injection** through cohort filter values.
- **Cross-site requests** from another origin trying to call your API.
- **Data leakage** via URL parameters into server logs.

**What we don't defend against:**

- An adversary who has physical or shell access to the machine running InsightPM.
- Adversarial multi-user scenarios (one user trying to read another user's data within the same install).
- Compromise of your Anthropic / Gemini account.
- Compromise of your GCP service account.

If your threat model is "untrusted users on the same instance," this tool is the wrong fit. Use Mixpanel/Amplitude or build a multi-tenant SaaS.

---

## What's protected

### Cohort filter SQL injection

Every filter value passed by the UI is bound as a parameterized BigQuery query parameter. **Values are never string-interpolated into SQL.**

Filter **fields** (column names like `geo.country`, `platform`) are validated against an allowlist of known-safe columns and discovered user-property / event-param keys. Attempting to specify a field outside the allowlist returns a 400 error.

This is covered by **9 dedicated tests** in `tests/test_cohort_filter.py`:

- Reject filters with embedded `;`, `--`, `DROP`, `UNION` in field names
- Reject filters with non-allowlisted columns
- Verify all values are bound (`@cohort_0`, etc.), not interpolated
- Verify the compiled SQL contains no value strings

### Shared password (optional)

Set `INSIGHTPM_PASSWORD` in `backend/.env` to gate all `/api/*` routes.

How it works:
1. User opens the app → frontend hits `/api/auth/status` (public) to learn auth is required.
2. User submits password → frontend hits `/api/auth/check` (public) to verify.
3. Backend returns the SHA-256 digest of the password.
4. Frontend stores the digest in `sessionStorage` (cleared on tab close).
5. All subsequent `/api/*` calls include `X-InsightPM-Auth: <digest>` header.
6. Backend compares against expected digest using `hmac.compare_digest` (constant-time).

The plain password never crosses the wire after the initial check. Even if someone shoulder-surfs your DevTools, they see the digest — which only works against your specific server.

This is **not a substitute for real auth.** It's defense against accidental discovery, not adversarial multi-user attack.

### CORS

The backend's CORS middleware allows requests only from `FRONTEND_ORIGIN` (configured in `.env`, defaults to `http://localhost:5173`). A browser on `evil.com` cannot make API calls to your localhost instance.

### URL parameter leakage

We never put cohort filters, user IDs, or other sensitive values in URL query strings — they'd end up in server logs and proxy referrer headers. Shareable URL state is encoded into the URL **hash** (`#s=...`), which:

- Never gets sent to the server
- Never appears in `Referer` headers when navigating

### Service account JSON storage

When you save a connection profile, the service account JSON is stored in SQLite at `~/.insightpm/insightpm.db`. **It is not encrypted at rest within the database.** The expectation is that:

- This is your machine, only you have shell access.
- File-level permissions on the SQLite file are enforced by the OS.
- If you need to share the DB (backup, transfer), you treat the file as sensitive.

If you need encryption-at-rest, the right approach is to use full-disk encryption (BitLocker, FileVault, LUKS) — not application-layer encryption of one file.

### LLM prompts

Every LLM system prompt is prepended with a topic guardrail:

> "You are an analytics assistant. Refuse politely if the question is unrelated to product analytics, user behavior, or the data shown."

This prevents the AI features from being used for off-topic content generation. It is not bulletproof — sufficiently motivated jailbreaking exists in the world. The point is to keep outputs predictable for normal use.

---

## What is NOT protected

### Multi-user data isolation

There is none. Anyone with the shared password (or anyone if no password is set) sees everything: all profiles, all saved cohorts, all funnels, all data.

### Encrypted-at-rest secrets

Neither `.env` nor the SQLite database is encrypted. They're protected by file permissions only.

### Rate limiting

No rate limits on API endpoints. Someone with valid auth (or no auth if disabled) could hammer the BigQuery API and run up your bill. In single-tenant local use this isn't a concern. If you expose this on the public internet, **don't** — or add a reverse proxy with rate limiting.

### CSRF

We don't use cookies, so traditional CSRF doesn't apply. The `X-InsightPM-Auth` header has to be set explicitly by JS, which can't happen from cross-origin without the user's collusion.

### XSS

User-controlled values (cohort filter values, profile names, etc.) are rendered through React, which auto-escapes. We never use `dangerouslySetInnerHTML` on user input. **One exception:** the SQL preview modal uses `dangerouslySetInnerHTML` to apply syntax highlighting — but that input comes from the backend, not from users, and contains only known-safe SQL.

---

## Reporting a security issue

**Do not file a public GitHub issue for security problems.**

Email <YOUR_EMAIL@example.com> with:

- A description of the issue
- Steps to reproduce
- A suggested fix if you have one

I'll acknowledge within a few days and work on a fix. For credible reports I'll credit you in the fix's commit (with your permission) or — at your preference — keep the report private.

There is no bug bounty. This is a side project.

---

## Recommendations for operators

If you're running this for a team:

1. **Set `INSIGHTPM_PASSWORD`** even on localhost. Cost: 30 seconds. Benefit: stops accidents.
2. **Don't expose the port to the internet.** If you need remote access, use a VPN or SSH tunnel (`ssh -L 8000:localhost:8000 your-server`).
3. **Use full-disk encryption** on the machine running InsightPM. Protects `.env` and the SQLite DB if the laptop is stolen.
4. **Rotate the service account JSON** periodically (every 90-180 days). Old keys → revoke in IAM Console.
5. **Rotate AI API keys** if they're ever pasted in a chat, logged, or otherwise exposed.
6. **Back up `~/.insightpm/insightpm.db`** somewhere safe. Losing it loses all your saved profiles, funnels, and cohorts. Use `python -m app.backup backup`.
