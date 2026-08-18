# ============================================================
#  FPL System - one-time setup
#  Run in PowerShell from inside the extracted fpl-system folder:
#      .\setup.ps1 -RepoUrl "https://github.com/YOURNAME/fpl-system.git"
# ============================================================
param(
    [Parameter(Mandatory=$true)]
    [string]$RepoUrl
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== FPL System setup ===" -ForegroundColor Cyan
Write-Host ""

# --- 1. check git ---
try {
    $v = git --version
    Write-Host "[ok] $v" -ForegroundColor Green
} catch {
    Write-Host "[X] Git is not installed." -ForegroundColor Red
    Write-Host "    Install it from https://git-scm.com/download/win then re-run."
    exit 1
}

# --- 2. sanity check we're in the right folder ---
if (-not (Test-Path "src\collect.py")) {
    Write-Host "[X] Run this from inside the fpl-system folder." -ForegroundColor Red
    Write-Host "    You should see src\, config\ and .github\ next to this script."
    exit 1
}
Write-Host "[ok] found project files" -ForegroundColor Green

# --- 3. warn if team_id not set ---
$settings = Get-Content "config\settings.yaml" -Raw
if ($settings -match "team_id:\s*null") {
    Write-Host "[!] team_id is still null in config\settings.yaml" -ForegroundColor Yellow
    Write-Host "    You can set it later - it is not needed for GW1."
}

# --- 4. init repo ---
if (Test-Path ".git") {
    Write-Host "[ok] git repo already initialised" -ForegroundColor Green
} else {
    git init | Out-Null
    git branch -M main
    Write-Host "[ok] initialised git repo" -ForegroundColor Green
}

# --- 5. remote ---
$existing = git remote 2>$null
if ($existing -contains "origin") {
    git remote set-url origin $RepoUrl
} else {
    git remote add origin $RepoUrl
}
Write-Host "[ok] remote set to $RepoUrl" -ForegroundColor Green

# --- 6. commit + push ---
git add .
git commit -m "FPL system v0.2 - minutes model, shrunk rates, DefCon" 2>&1 | Out-Null
Write-Host "[ok] committed" -ForegroundColor Green

Write-Host ""
Write-Host "Pushing... (a browser or credential prompt may appear)" -ForegroundColor Cyan
git push -u origin main

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host ""
Write-Host "Now finish in your browser:" -ForegroundColor Cyan
Write-Host "  1. Open your repo -> Settings -> Actions -> General"
Write-Host "     Workflow permissions -> 'Read and write permissions' -> Save"
Write-Host "     (Skip this and the collector fails silently.)"
Write-Host ""
Write-Host "  2. Actions tab -> enable workflows if prompted"
Write-Host ""
Write-Host "  3. Actions -> 'backfill' -> Run workflow   (builds 7 seasons of history)"
Write-Host "  4. Actions -> 'collect'  -> Run workflow   (starts the hourly logger)"
Write-Host "  5. Actions -> 'report'   -> Run workflow   (writes reports/latest.md)"
Write-Host ""
