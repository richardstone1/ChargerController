# Push **ChargerController** to GitHub

Run these on your PC (Git Bash, PowerShell, or VS Code terminal). This repo is **MIT-licensed** and includes **credits** to upstream OBI work — see `LICENSE`, `CREDITS.md`, and `CONTRIBUTING.md`.

## 1. Put source files in this folder

From `Cursor Projects` (parent folder), copy into `ChargerController`:

- `main.py`
- `obi.py`
- `control.html` (optional)

Example (PowerShell):

```powershell
cd "$env:USERPROFILE\Documents\Cursor Projects"
Copy-Item -Force main.py, obi.py, control.html -Destination .\ChargerController\
```

## 2. Initialize and commit

```powershell
cd "$env:USERPROFILE\Documents\Cursor Projects\ChargerController"
git init
git add .
git commit -m "Initial commit: Pico W ChargerController firmware"
```

## 3. Create the repo on GitHub

- In the browser: **GitHub → New repository → Repository name: `ChargerController` → Create** (no README if you already committed locally).

Or with [GitHub CLI](https://cli.github.com/) (`gh auth login` first):

```powershell
gh repo create ChargerController --public --source=. --remote=origin --push
```

## 4. Push manually (if you created an empty repo on the web)

```powershell
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ChargerController.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

## Private repo

Use `--private` with `gh repo create`, or set visibility in the GitHub UI.
