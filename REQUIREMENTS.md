# Requirements

Everything you need installed on your machine before running InsightPM.

This document is for someone setting up the tool for the first time. If you already have Python, Node, and a Firebase project with BigQuery export, skip to [SETUP.md](SETUP.md).

---

## At a glance

| What | Why | Required? |
|---|---|---|
| **Python 3.12** | Backend runtime | Yes |
| **Node.js 20+** | Frontend runtime + npm package manager | Yes |
| **Git** | Cloning the repo | Yes |
| **A Firebase project with BigQuery export enabled** | The actual data source | Yes |
| **A GCP service account JSON** | Read-only access to BigQuery | Yes |
| **Docker Desktop** | Optional easier setup path | No (alternative to Python/Node) |
| **An Anthropic or Gemini API key** | Powers AI features | Recommended (tool works without, falls back to templates) |
| **A code editor** (VS Code etc.) | If you plan to modify code | Optional |

---

## 1. Python 3.12 — required

**Why not 3.13 or 3.14?** Pydantic and some other dependencies don't have pre-built wheels for the very newest Python on Windows yet, leading to compilation errors that require Rust + Visual Studio Build Tools. Python 3.12 has wheels for everything and just works.

### Windows

1. Download the **64-bit installer** from https://www.python.org/downloads/release/python-3128/ (look in the "Files" section near the bottom of the page)
2. Run the installer
3. **Important options during install:**
   - ✅ "Add python.exe to PATH" — check this if 3.12 is your only Python. UNCHECK it if you also have Python 3.13 / 3.14 installed and don't want 3.12 to override them globally.
   - ✅ "Install for all users" (your choice)
   - Click "Customize installation" → keep defaults → Install
4. Verify in PowerShell:
   ```powershell
   py -3.12 --version
   # Should print: Python 3.12.x
   ```

If you have multiple Python versions, **always use `py -3.12` to invoke 3.12 specifically.**

### macOS

```bash
# Using Homebrew (recommended)
brew install python@3.12

# Verify
python3.12 --version
```

If you don't have Homebrew, install it from https://brew.sh first.

### Linux

```bash
# Ubuntu/Debian 24.04 and newer have 3.12 in apt
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev

# Verify
python3.12 --version
```

For older distros, use [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa) or [pyenv](https://github.com/pyenv/pyenv).

---

## 2. Node.js 20 or newer — required

This includes `npm`, which is what installs the frontend dependencies.

### Windows / macOS / Linux

The easiest cross-platform path:

1. Go to https://nodejs.org/
2. Download the **LTS version** (currently 20.x or 22.x — both fine)
3. Run the installer with default options
4. Verify:
   ```bash
   node --version
   # Should print: v20.x.x or v22.x.x
   npm --version
   # Should print: 10.x.x or higher
   ```

Alternative for Mac/Linux: install via [nvm](https://github.com/nvm-sh/nvm) if you need to switch Node versions:
```bash
nvm install 20
nvm use 20
```

---

## 3. Git — required

For cloning the repo.

- **Windows**: https://git-scm.com/download/win — install with defaults
- **macOS**: comes with Xcode Command Line Tools (`xcode-select --install`) or via `brew install git`
- **Linux**: `sudo apt install git`

Verify:
```bash
git --version
```

---

## 4. Firebase / BigQuery setup — required

InsightPM reads data from BigQuery, not directly from Firebase. So you need to set up the BigQuery export first.

### Step 4a: Enable BigQuery export in Firebase

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Pick your project
3. Click the gear icon → **Project settings**
4. Open the **Integrations** tab
5. Find **BigQuery** → click **Manage**
6. Enable the integration for **Google Analytics**
7. Pick an export location (close to your users for lower latency)
8. Click **Link**

**Important: data only flows forward from this day.** There's no historical backfill. Wait at least 24 hours after enabling export before continuing — Firebase runs the first daily export overnight.

### Step 4b: Find your Project ID and Dataset ID

- **Project ID**: in Firebase Console → Project settings → General → Project ID (looks like `my-app-1a2b3`)
- **Dataset ID**: open [BigQuery Console](https://console.cloud.google.com/bigquery) → expand your project → you'll see a dataset named `analytics_NNNNNNNNN` (a 9-digit number). That's your dataset ID.

You'll plug both of these into the `.env` file later.

### Step 4c: Create a service account with read-only access

InsightPM authenticates to BigQuery using a service account JSON file. The service account needs **minimum-required permissions** — just enough to run queries.

1. Open [Google Cloud Console → IAM & Admin → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Make sure the project at the top matches your Firebase project
3. Click **+ CREATE SERVICE ACCOUNT**
4. Name it `insightpm-reader` (or anything you'll recognize)
5. Click **CREATE AND CONTINUE**
6. Add these two roles (and only these two):
   - **BigQuery Data Viewer** — to read your event tables
   - **BigQuery Job User** — to run queries
7. Click **CONTINUE** → **DONE**
8. Click on the new service account in the list
9. Open the **KEYS** tab → **ADD KEY** → **Create new key** → **JSON** → **CREATE**
10. A JSON file downloads. **Keep this file safe** — anyone with it can read your analytics data.
11. Move it somewhere stable, like `C:\insightpm-secrets\service-account.json` (Windows) or `~/insightpm-secrets/service-account.json` (Mac/Linux)

You'll point InsightPM to this file via the `.env` later.

---

## 5. AI provider key — optional but recommended

Without an AI key, InsightPM still works — but the User Behavior Profile, "Explain why", and Investigator features fall back to deterministic templated text instead of LLM-generated narratives. The templated text is genuinely useful (the tool's deterministic SQL gives you all the numbers regardless), but the AI version is dramatically better.

### Option A: Anthropic Claude (recommended)

1. Sign up at https://console.anthropic.com/
2. Add billing details (Claude doesn't have a free tier, but light personal use costs <$1/month)
3. Go to https://console.anthropic.com/settings/keys
4. Click **Create Key**, name it `insightpm`, copy the key (starts with `sk-ant-api03-...`)
5. Save this key — you'll paste it into your `.env`

Approximate cost: each User Behavior Profile generation costs around $0.001-0.005 in API charges. The Investigator costs around $0.005 per investigation. Light personal use (10-50 calls/day) stays under $1/month.

### Option B: Google Gemini (free tier available)

1. Sign up at https://aistudio.google.com/
2. Click **Get API key** → **Create API key in new project**
3. Copy the key (starts with `AIza...`)
4. Save it — you'll paste it into your `.env`

Gemini has a free tier (1500 requests/day on Flash 2.0 as of writing). Generous for personal use.

### Both are fine

InsightPM is provider-agnostic — set either `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` in `.env`. If both are set, Gemini is tried first, then Anthropic. The architecture makes adding more providers easy (see [ARCHITECTURE.md](ARCHITECTURE.md)).

---

## 6. Docker — optional (alternative to Python + Node)

If you'd rather not install Python and Node directly, Docker handles both.

### Windows / macOS

1. Download **Docker Desktop** from https://www.docker.com/products/docker-desktop
2. Run the installer
3. Start Docker Desktop and wait for the whale icon to settle in your system tray
4. Verify in your terminal:
   ```bash
   docker --version
   docker compose version
   ```

### Linux

```bash
# Ubuntu
sudo apt install docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# log out and back in
```

With Docker installed, the setup becomes a one-liner — see [SETUP.md](SETUP.md).

---

## Disk space and RAM requirements

This is a lightweight tool. Reasonable minimums:

- **Disk**: 500 MB for the project + dependencies (1.5 GB if you use Docker images)
- **RAM**: 2 GB free when running (1 GB backend + ~500 MB frontend dev server)
- **Internet**: required for BigQuery API calls and AI API calls

It runs fine on any modern laptop. No GPU needed — the LLM runs in Anthropic / Google's cloud, not locally.

---

## Verification checklist

Before moving to [SETUP.md](SETUP.md), confirm:

- [ ] `py -3.12 --version` prints `Python 3.12.x` (or `python3.12 --version` on Mac/Linux)
- [ ] `node --version` prints `v20.x.x` or higher
- [ ] `npm --version` prints `10.x.x` or higher
- [ ] `git --version` prints something
- [ ] Your Firebase project has BigQuery export enabled (you set this up >24 hours ago, or you're willing to wait)
- [ ] You have your `BQ_PROJECT_ID` (looks like `my-app-1a2b3`)
- [ ] You have your `BQ_DATASET_ID` (looks like `analytics_123456789`)
- [ ] You have a service account JSON file saved somewhere on disk
- [ ] You have an Anthropic OR Gemini API key (or you're OK with templated fallbacks)

If all of those are ✅, head to [SETUP.md](SETUP.md).

---

## Troubleshooting prerequisites

**"py is not recognized" on Windows** → Python wasn't added to PATH. Reinstall and check the "Add to PATH" box, or use the full path (e.g. `C:\Python312\python.exe`).

**"pip install fails with 'Microsoft Visual C++ 14.0 or greater required'"** → You're on Python 3.13 or 3.14. Downgrade to 3.12.

**"docker: command not found"** → Docker Desktop needs to be running, not just installed. Start it from your Applications / Start Menu.

**BigQuery says "Dataset not found"** → Your `BQ_DATASET_ID` is wrong, or BigQuery export hasn't completed its first daily run yet. Wait 24 hours after enabling.

**Service account has the wrong permissions** → Go back to step 4c and verify the two roles are exactly **BigQuery Data Viewer** and **BigQuery Job User**.
