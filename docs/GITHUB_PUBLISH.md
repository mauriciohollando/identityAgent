# Publish this repository to GitHub

## One-time setup

1. Create a **new empty** repository on GitHub (no README if you will push an existing tree), e.g. `identityAgent`.
2. From your laptop, in the project root:

```bash
git init
git branch -M main
git remote add origin https://github.com/mauriciohollando/identityAgent.git
git add -A
git status   # verify no .env or *.db
git commit -m "Initial publish: Trust Auditor"
git push -u origin main
```

3. Replace any remaining placeholders (e.g. production Cloud Run URL in the agent card if it changes).

4. In GitHub: **Settings → Secrets and variables → Actions** if you add deploy workflows later.

5. Enable **branch protection** on `main` and require the **CI** check (after first successful run).

## Secret scanning

Before pushing, confirm:

```bash
git log --all --full-history -- "*.env" || true
rg -n "sk_live_|whsec_|BEGIN PRIVATE" --glob '!.venv/**' || true
```

Rotate any credential that was ever committed or pasted into chat logs.
