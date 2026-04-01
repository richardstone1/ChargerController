# Initial git commit for ChargerController (run from this folder after Git is installed).
# Usage: powershell -ExecutionPolicy Bypass -File .\make-commit.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    $candidates = @(
        "C:\Program Files\Git\bin\git.exe",
        "C:\Program Files (x86)\Git\bin\git.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { $git = @{ Source = $p }; break }
    }
}
if (-not $git) {
    Write-Host "Git not found. Install from https://git-scm.com/download/win then re-run this script."
    exit 1
}

$exe = if ($git.Source) { $git.Source } else { $git.Path }
& $exe init
& $exe add .
& $exe commit -m @"
Initial commit: Pico W ChargerController (MIT)

Open source; OBI layer credits Martin Jansson / Open Battery Information.
See CREDITS.md, LICENSE, CONTRIBUTING.md.
"@
Write-Host "Done. Create GitHub repo 'ChargerController' and: git remote add origin <url> && git push -u origin main"
