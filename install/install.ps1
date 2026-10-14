# Install these skills globally for opencode.
#
#   .\install.ps1              # install every skill in this repo
#   .\install.ps1 -Skill pbix-report-authoring
#   .\install.ps1 -Link       # symlink instead of copy (edits reflect immediately)
#
# Restart opencode afterwards - skills are loaded at startup.

[CmdletBinding()]
param(
    [string]$Skill = "",
    [switch]$Link,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $repoRoot "skills"

# opencode reads user-level skills from ~/.config/opencode/skills
$targetRoot = Join-Path $HOME ".config\opencode\skills"

Write-Host "Source : $sourceRoot" -ForegroundColor DarkGray
Write-Host "Target : $targetRoot" -ForegroundColor DarkGray
Write-Host ""

if (-not (Test-Path -LiteralPath $sourceRoot)) {
    throw "No 'skills' directory found at $sourceRoot"
}

if ($Skill) {
    $skills = @($Skill)
} else {
    $skills = @(Get-ChildItem -LiteralPath $sourceRoot -Directory | Select-Object -ExpandProperty Name)
}

if ($skills.Count -eq 0) {
    Write-Host "No skills to install." -ForegroundColor Yellow
    return
}

New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null

foreach ($name in $skills) {
    $src = Join-Path $sourceRoot $name
    $dst = Join-Path $targetRoot $name

    if (-not (Test-Path -LiteralPath (Join-Path $src "SKILL.md"))) {
        Write-Warning "skip $name - no SKILL.md"
        continue
    }

    if (Test-Path -LiteralPath $dst) {
        if (-not $Force) {
            Write-Warning "skip $name - already installed (use -Force to overwrite)"
            continue
        }
        Remove-Item -LiteralPath $dst -Recurse -Force
    }

    if ($Link) {
        New-Item -ItemType SymbolicLink -Path $dst -Target $src | Out-Null
        Write-Host "linked  $name" -ForegroundColor Green
    }
    else {
        Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
        Write-Host "copied  $name" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Done. Restart opencode to pick up the skill(s)." -ForegroundColor Cyan