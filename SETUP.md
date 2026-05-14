# Setup

Step-by-step first-time setup for InsightPM. Assumes you've completed everything in [REQUIREMENTS.md](REQUIREMENTS.md) (Python 3.12, Node 20+, Git all installed).

Total time: 20-40 minutes depending on whether you've used Google Cloud before.

---

## Big picture

You're going to:

1. Enable BigQuery export in Firebase Console (if not already)
2. Wait 24 hours for the first export to land (only the first time)
3. Create a Google Cloud service account with read-only BigQuery access
4. Download the service account JSON
5. Clone this repo
6. Configure environment variables
7. Run the backend and frontend
8. Add a connection profile in the UI

Steps 1-4 are one-time per Firebase project. Steps 5-8 are the per-machine setup.

---

## Part 1: Firebase BigQuery export

If your Firebase project already has BigQuery export enabled, skip to Part 2.

### Step 1.1: Enable the export

1. Go to <https://console.firebase.google.com/> and pick your project.
2. Click the gear icon (top-left) → **Project Settings**.
3. Click the **Integrations** tab at the top.
4. Find **BigQuery** in the list → click **Manage** (or **Link**).
5. Check the boxes for the Firebase products whose data you want exported. **Analytics** is the one this tool reads.
6. Choose your billing project (if you don't have one, you'll need to add a billing account — the BigQuery free tier covers most personal use, but Firebase requires the link).
7. Choose **Daily** export frequency. **Streaming** also works if you want intraday data, but we don't read it.
8. Click **Link to BigQuery**.

### Step 1.2: Wait 24 hours

Firebase doesn't backfill historical data. Once you enable export, **data only flows forward from the day you enabled it.** The first daily export lands within ~24 hours.

You can check whether export is working by going to:
- <https://console.cloud.google.com/bigquery>
- In the left panel, expand your project → look for a dataset called `analytics_NNNNNNNNN` (where N is your Firebase project's number).
- Inside, you should see `events_YYYYMMDD` tables appearing once per day.

If after 48 hours nothing has appeared, double-check that the link in Firebase Console shows "Active" and that your app is actually sending events (check **Realtime** in Firebase Analytics).

### Step 1.3: Note your project and dataset IDs

You'll need these later. Find them at:

- <https://console.cloud.google.com/bigquery>
- Left panel → expand your project. The **project ID** is the name of the project (e.g., `my-app-12345`).
- The **dataset ID** is the analytics dataset (e.g., `analytics_514396744`).

Write them down. You'll paste them into `.env` shortly.

---

## Part 2: Service account

The tool needs a Google Cloud service account to read BigQuery. Service accounts are how non-human tools authenticate — like a username/password but for software.

### Step 2.1: Create the service account

1. Go to <https://console.cloud.google.com/iam-admin/serviceaccounts>.
2. Make sure the **project selector** at the top is set to the same project that owns your Firebase BigQuery dataset.
3. Click **+ CREATE SERVICE ACCOUNT** at the top.
4. **Name:** `insightpm-reader` (anything works).
5. **Description:** "Read-only access for InsightPM analytics tool."
6. Click **CREATE AND CONTINUE**.

### Step 2.2: Grant roles

On the next screen ("Grant this service account access to project"):

Add **two** roles:

1. **BigQuery Data Viewer** — lets the tool read tables.
2. **BigQuery Job User** — lets the tool run queries.

Both are required. Just one of them isn't enough.

Click **CONTINUE**, then **DONE**.

### Step 2.3: Generate the JSON key

1. You're now on the Service Accounts list. Click the `insightpm-reader` email in the list.
2. Click the **KEYS** tab at the top.
3. Click **ADD KEY → Create new key**.
4. Choose **JSON**.
5. Click **CREATE**.

Your browser downloads a `.json` file. **This file is your credential** — anyone with it can read your BigQuery data. Treat it like a password.

Move it somewhere safe, e.g.:
- Windows: `C:\Users\<you>\.insightpm-keys\sa.json`
- macOS/Linux: `~/.insightpm-keys/sa.json`

Note the full path. You'll need it next.

---

## Part 3: Clone and configure

### Step 3.1: Clone the repo

Pick a directory you'd like the code to live in. On Windows, something like `D:\Project\` works.

```powershell
# Windows
cd D:\Project
git clone https://github.com/YOUR_USERNAME/insightpm.git
cd insightpm
```

```bash
# macOS / Linux
cd ~/Projects
git clone https://github.com/YOUR_USERNAME/insightpm.git
cd insightpm
```

### Step 3.2: Configure environment variables

```powershell
# Windows
cd backend
copy .env.example .env
notepad .env
```

```bash
# macOS / Linux
cd backend
cp .env.example .env
nano .env       # or vim, code, etc.
```

Fill in these values:

```
BQ_PROJECT_ID=your-project-id-here
BQ_DATASET_ID=analytics_NNNNNNNNN
FRONTEND_ORIGIN=http://localhost:5173

# Pick ONE of these for AI features (optional but recommended):
GEMINI_API_KEY=AIza...
# or
ANTHROPIC_API_KEY=sk-ant-api03-...

# Optional shared password protection:
# INSIGHTPM_PASSWORD=your-team-password
```

**Important on Windows:** Notepad sometimes saves the file as `.env.txt` instead of `.env`. Verify with `dir` — you should see exactly `.env` with no extension. If you see `.env.txt`, rename it.

### Step 3.3: Point to your service account JSON

You have two choices.

**Option A — Set the path in `.env`:**

```
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\<you>\.insightpm-keys\sa.json
```

The path needs forward slashes or doubled backslashes. The standard Windows backslash works, but it must be quoted carefully if it contains spaces.

**Option B — Add the connection through the UI later (recommended):**

Skip this for now. Once the app is running, the connection form will let you paste the JSON content directly. It gets saved to your local SQLite, encrypted-at-rest is your filesystem's job.

---

## Part 4: Run the backend

### Step 4.1: Create the virtual environment

```powershell
# Windows
cd D:\Project\insightpm\backend
py -3.12 -m venv venv
venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
cd ~/Projects/insightpm/backend
python3.12 -m venv venv
source venv/bin/activate
```

After activation your prompt should show `(venv)` at the start.

### Windows PowerShell trap

If you see:

```
File ... cannot be loaded because running scripts is disabled on this system.
```

Run this once to allow scripts:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then retry `venv\Scripts\Activate.ps1`.

### Step 4.2: Install dependencies

```powershell
pip install -r requirements.txt
```

Takes 30-60 seconds. If it fails with mention of `link.exe` or `cargo`, **you're on Python 3.13/3.14**. Go back to [REQUIREMENTS.md](REQUIREMENTS.md) and install 3.12 specifically.

### Step 4.3: Start the server

```powershell
uvicorn app.main:app --reload --port 8000
```

You should see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

Leave this window running.

---

## Part 5: Run the frontend

Open a **new terminal** (keep the backend running).

### Step 5.1: Install dependencies

```powershell
cd D:\Project\insightpm\frontend
npm install
```

Takes 1-2 minutes. Downloads ~150 MB of node_modules. One-time cost.

### Step 5.2: Start the dev server

```powershell
npm run dev
```

You should see:

```
  VITE v5.4.x  ready in 432 ms
  ➜  Local:   http://localhost:5173/
```

Leave this window running too.

---

## Part 6: Open the app and connect

1. Open <http://localhost:5173> in your browser.
2. (If you set `INSIGHTPM_PASSWORD`) Enter the password.
3. You'll see the **Connection** screen.
4. Either:
   - Paste your service account JSON content directly into the field, OR
   - If you set `GOOGLE_APPLICATION_CREDENTIALS` in `.env`, the tool should auto-detect — just confirm the project + dataset IDs.
5. Click **Save as profile** to save this connection for future restarts.
6. Click **Connect**.

If everything works, you'll land on the dashboard. The Insights panel will start loading.

---

## Common issues

### "BigQuery dataset or table not found"

- The `BQ_DATASET_ID` in `.env` doesn't match an actual dataset. Double-check the BigQuery console.
- Make sure it's the **dataset ID** (`analytics_514396744`), not the project ID.

### "Permission denied" / "403"

- The service account is missing one of the two required roles. Go back to <https://console.cloud.google.com/iam-admin/iam>, find your `insightpm-reader@...iam.gserviceaccount.com`, click the edit pencil, and add the missing role.

### "No events found" / empty charts

- Your BigQuery export was enabled recently and yesterday's table doesn't exist yet. Wait until tomorrow morning.
- Your app isn't sending events. Check Firebase Analytics → Realtime to verify event flow.

### Investigator is slow (10-25 seconds)

- That's normal. It runs 6 BigQuery queries in parallel + 1 LLM call.
- Subsequent investigations of the same insight hit the 30-minute cache and return in <1 second.

### Frontend shows blank page

- Open browser DevTools (F12) → Console tab.
- Look for red errors mentioning module imports — usually means `npm install` didn't complete. Rerun it.

### Anthropic SDK error: "unexpected keyword argument 'proxies'"

- `anthropic` and `httpx` versions are mismatched. Run:
  ```powershell
  pip install --upgrade anthropic httpx
  ```

---

## What's next

You're running. From the dashboard you can:

- Build a **funnel** for your key conversion event
- Look at **retention** cohorts
- Pick a recent user and run a **User Behavior Profile**
- Click any fired **insight** to **Investigate** it

For day-to-day operations (backup/restore, log rotation, updating to a new version), see the bottom of [README.md](README.md).

For understanding what you're looking at and how it works internally, see [ARCHITECTURE.md](ARCHITECTURE.md).

For known limitations and design decisions, see [TRADEOFFS.md](TRADEOFFS.md).
