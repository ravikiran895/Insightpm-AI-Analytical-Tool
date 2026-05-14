# Contributing

Thanks for your interest. This is a personal project shared in the hope it's useful — but I welcome issues, PRs, and ideas.

---

## Filing an issue

Before opening an issue, please:

1. Check existing [issues](https://github.com/YOUR_USERNAME/insightpm/issues) to see if it's already reported.
2. Try to reproduce on a clean install.

When filing:

- **Bug reports** should include: OS, Python version, Node version, what you did, what you expected, what happened (with full error message if any).
- **Feature requests** should describe: the workflow you're trying to support, why the existing tool doesn't, and a rough sketch of what success would look like.

---

## Pull requests

PRs are very welcome. Some guidelines:

### Small, focused PRs

Easier to review and ship. If you're working on something larger than ~200 lines of code, open an issue first to discuss the approach.

### Tests

Every behavior change should come with a test. The bar is "if this regresses, would a test catch it?"

```bash
cd backend
python -m pytest tests/         # full suite, ~5 seconds
python -m pytest tests/ -v      # verbose
python -m pytest tests/test_X.py # one file
```

The test suite is fast on purpose. Keep it that way — no real BigQuery calls, no real LLM calls. Mock both.

### Style

- Python: follow PEP 8. Keep functions short, prefer pure functions, name things clearly.
- Frontend: keep components small. State lives in the smallest scope that needs it. No new state libraries.
- Both: comments explain *why*, not *what*. Read the existing services — they're commented in this style.

### Things to avoid

- Don't add a new dependency without checking it's worth it (size, maintenance, security surface).
- Don't break the SQL/AI separation. The LLM never produces numbers — keep it that way.
- Don't add `console.log` or `print` debug lines to committed code. Use the logger.
- Don't commit `.env`, service account JSON, or any other credential file.

---

## Dev environment

### One-time setup

```bash
git clone https://github.com/YOUR_USERNAME/insightpm.git
cd insightpm/backend
python3.12 -m venv venv
# Windows: venv\Scripts\Activate.ps1
# Unix:    source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest, etc.

cd ../frontend
npm install
```

### Day-to-day

Two terminals:

```bash
# Terminal 1
cd backend
source venv/bin/activate    # or venv\Scripts\Activate.ps1 on Windows
uvicorn app.main:app --reload --port 8000
```

```bash
# Terminal 2
cd frontend
npm run dev
```

### Running tests before PR

```bash
cd backend
python -m pytest tests/
```

All 117 tests must pass. If you add a feature, add tests.

---

## Roadmap items

If you're looking for something to work on, see the **Roadmap** section in [TRADEOFFS.md](TRADEOFFS.md). Short list:

- Email/property search for users (high-value)
- Auto-discovered behavior patterns (high-value, larger scope)
- Slack/email weekly digest
- Mobile-responsive UI
- First-run onboarding wizard
- GitHub Actions CI for the test suite

Open an issue to claim one before starting — saves us both effort if someone else is already working on it.

---

## Security

If you find a security issue, **do not file a public issue**. See [SECURITY.md](SECURITY.md).

---

## Code of conduct

Be kind, be specific, assume good intent. That's it.
