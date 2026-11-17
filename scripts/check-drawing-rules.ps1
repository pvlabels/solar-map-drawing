# Run from any directory: pwsh -File scripts/check-drawing-rules.ps1
# Compare unchanged historical paragraphs and individual bullets verbatim.
# Joined panels (3.2.0), equipment (3.3.0/3.3.2), white leader backing
# (3.3.1), orbiting north labels (3.3.3), full-area roads (3.3.4), and
# array wording (3.3.5) intentionally replace the narrow blocks listed below.
# Renderer behavior is checked by python -m unittest discover -s tests -v.
param(
    [string]$SourceRef = 'ae46c293ea15e3edef497f983deeaa1fc4f76f84',
    [string]$ReferencesDirectory = (Join-Path $PSScriptRoot '../plugins/solar-map-drawing/skills/solar-map-drawing/references'),
    # Optional pinned baseline for validating an exported snapshot without .git.
    [string]$OriginalRulesFile
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$sourcePath = 'plugins/solar-map-drawing/skills/solar-map-drawing/references/drawing-rules.md'
if ($OriginalRulesFile) {
    $original = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $OriginalRulesFile).Path)
} else {
    $original = & git -C $repo show "${SourceRef}:$sourcePath"
    if ($LASTEXITCODE -ne 0) { throw "Cannot read original drawing rules at $SourceRef" }
    $original = $original -join "`n"
}

$supersededPrefixes = @(
    '- **Panels:**',
    '- **Equipment:**',
    '- **North:**',
    'Roof accuracy is a topology check:',
    '- At necessary geometry crossings use actual trimmed vector clearances,',
    'Final artwork must be loose editable paths/text:',
    'Draw streets **only at 0, 90, 180 or 270 degrees in the final output**.',
    'Retain the solid near edge plus parallel dashed outer edge.',
    'Use uppercase Arial/Helvetica by default,'
)

function Get-Paragraphs([string]$Content) {
    # Split bullets independently so changed crossing/N rules cannot hide changes
    # to the neighboring arrow, rotation, wall, or source-preservation rules.
    [regex]::Split($Content.Replace("`r`n", "`n").Trim("`n"), '\n[\t ]*\n|\n(?=- )') |
        Where-Object {
            $block = $_
            $replaced = $false
            foreach ($prefix in $supersededPrefixes) {
                if ($block.StartsWith($prefix, [StringComparison]::Ordinal)) { $replaced = $true; break }
            }
            $block.Length -gt 0 -and !$replaced
        }
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

$paragraphs = @(Get-Paragraphs $original)
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
Write-Output "PASS: all $($paragraphs.Count) unchanged original rule blocks preserved across $($files.Count) files; intentional replacements documented above and renderer behavior covered by unit tests."
