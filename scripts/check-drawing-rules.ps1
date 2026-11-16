# Run from any directory: pwsh -File scripts/check-drawing-rules.ps1
# Compare unchanged historical paragraphs verbatim (normalizing line endings only).
# The Panels paragraph was intentionally superseded by joined-array rules in 3.2.0;
# tests/test_panel_arrays.py verifies the replacement behavior.
param(
    [string]$SourceRef = 'ae46c293ea15e3edef497f983deeaa1fc4f76f84',
    [string]$ReferencesDirectory = (Join-Path $PSScriptRoot '../plugins/solar-map-drawing/skills/solar-map-drawing/references')
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$sourcePath = 'plugins/solar-map-drawing/skills/solar-map-drawing/references/drawing-rules.md'
$original = & git -C $repo show "${SourceRef}:$sourcePath"
if ($LASTEXITCODE -ne 0) { throw "Cannot read original drawing rules at $SourceRef" }

function Get-Paragraphs([string]$Content) {
    $unchanged = [regex]::Replace($Content.Replace("`r`n", "`n"), '(?m)^- \*\*Panels:\*\*[^\n]*(?:\n|$)', '')
    [regex]::Split($unchanged.Trim("`n"), '\n[\t ]*\n') |
        Where-Object { $_.Length -gt 0 }
}

$files = @(
    Get-Item -LiteralPath (Join-Path $ReferencesDirectory 'drawing-rules.md')
    Get-ChildItem -LiteralPath $ReferencesDirectory -Filter 'drawing-rules-*.md' -File
)
$counts = [Collections.Generic.Dictionary[string, int]]::new([StringComparer]::Ordinal)
foreach ($file in $files) {
    foreach ($paragraph in (Get-Paragraphs ([IO.File]::ReadAllText($file.FullName)))) {
        if (!$counts.ContainsKey($paragraph)) { $counts[$paragraph] = 0 }
        $counts[$paragraph]++
    }
}

$paragraphs = @(Get-Paragraphs ($original -join "`n"))
$missing = @(
    foreach ($paragraph in $paragraphs) {
        if ($counts.ContainsKey($paragraph) -and $counts[$paragraph] -gt 0) {
            $counts[$paragraph]--
        } else {
            $paragraph
        }
    }
)
if ($missing.Count -gt 0) {
    foreach ($paragraph in $missing) {
        [Console]::Error.WriteLine("Missing or changed paragraph:`n$paragraph`n")
    }
    throw "$($missing.Count) original paragraph(s) missing or changed."
}
Write-Output "PASS: all $($paragraphs.Count) unchanged original paragraphs preserved across $($files.Count) files; panel-rule replacement covered by geometry tests."
