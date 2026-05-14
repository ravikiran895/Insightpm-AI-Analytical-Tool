# Pushing to GitHub — first time

You have a clean, secret-free project. Here's how to publish it.

## 1. Create the repo on GitHub

1. Go to <https://github.com/new>
2. Repository name: `insightpm` (or whatever you prefer)
3. **Public** (or Private — your choice; Public is recommended for portfolio value)
4. **Do NOT** initialize with README, .gitignore, or license — you already have those.
5. Click **Create repository**.

GitHub shows you a page with quick-setup commands. Use the **"push an existing repository from the command line"** section.

## 2. From your project folder

```powershell
# Make sure you're in the project root (where README.md lives)
cd D:\Project\insightpm

# Initialize git (if not already)
git init

# Stage everything (respects .gitignore)
git add .

# Sanity check — make sure no secrets are staged
git status
# Look at the file list. You should NOT see: .env, venv/, node_modules/, *.json (service account)
# If you do, STOP and add them to .gitignore before continuing.

# First commit
git commit -m "Initial public release: InsightPM v0.9.2"

# Link to GitHub (replace YOUR_USERNAME)
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/insightpm.git

# Push
git push -u origin main
```

## 3. After the first push

1. Visit your repo on GitHub.
2. Open `README.md` — verify it renders nicely.
3. **Update placeholders:** Replace every `YOUR_USERNAME` and `YOUR_EMAIL@example.com` with your actual values.
   ```powershell
   # On Windows, easiest is to edit each file in Notepad/VS Code:
   # - README.md
   # - CONTRIBUTING.md
   # - SECURITY.md
   # - docs/screenshots/README.md
   ```

4. Commit and push the updates:
   ```powershell
   git add .
   git commit -m "docs: replace placeholder GitHub username"
   git push
   ```

## 4. Add screenshots

1. Take 3 screenshots: User Profile, Investigator, Architecture diagram.
2. Save as `docs/screenshots/user-profile.png`, `docs/screenshots/investigator.png`, `docs/screenshots/architecture.png`.
3. Update README.md if the filenames differ.
4. Commit and push:
   ```powershell
   git add docs/screenshots/
   git commit -m "docs: add product screenshots"
   git push
   ```

## 5. Repo polish (optional but worth 5 minutes)

On the GitHub repo page:

- Click the **gear icon** next to "About" (top-right of repo page).
- **Description:** `Self-hosted product analytics with AI-generated user behavior narratives. Built on Firebase / GA4 BigQuery export.`
- **Website:** (leave blank or point to your LinkedIn post)
- **Topics:** `product-analytics`, `firebase-analytics`, `bigquery`, `ai`, `claude`, `gemini`, `pm-tools`, `self-hosted`, `python`, `react`, `fastapi`
- Save changes.

These topics show up in GitHub search and on your profile.

## 6. Add a release tag (optional)

Tagging v0.9.2 makes the release official:

```powershell
git tag -a v0.9.2 -m "v0.9.2 — math audit + Where/When/Why investigator"
git push origin v0.9.2
```

Then on GitHub: **Releases → Draft a new release → Choose tag v0.9.2 → publish.** Paste the v0.9.2 entry from `CHANGELOG.md` as the release notes.

---

## After it's live

Share the link. Common places:

- Your LinkedIn post — reply in the comments with the GitHub URL
- Your LinkedIn profile **Featured** section
- Your resume / portfolio

## What to do when you push updates later

Day-to-day:

```powershell
# Make changes
git add .
git commit -m "feat: short description"
git push
```

Versioned release:

```powershell
git tag -a v0.10.0 -m "v0.10.0 — your changes"
git push origin v0.10.0
```

That's it.

---

**This file** (`PUBLISH.md`) is a one-time guide. Once your repo is live, you can delete it or keep it as a memory aid.
