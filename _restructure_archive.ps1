<#
.SYNOPSIS
Restructure an existing photo archive: canonicalise names, group every
"__TO_SPLIT__" folder in the GUI, canonicalise again, then check and fix
compliance with ARCHIVE_STANDARD.md (those last two not implemented yet -
the standard is still a v0.1 draft).

.DESCRIPTION
The PowerShell twin of _restructure_archive.bat. Same tool, same arguments,
same exit codes - every switch is passed straight through to
tools\restructure_archive.py, so its --help is the reference.

Nothing is changed without --apply. With no arguments this is a dry run over
the configured archive root's current year. "--year ALL" runs every year the
root holds, oldest first, one run each.

.EXAMPLE
.\_restructure_archive.ps1
.EXAMPLE
.\_restructure_archive.ps1 --apply
.EXAMPLE
.\_restructure_archive.ps1 --year ALL
.EXAMPLE
.\_restructure_archive.ps1 "d:\__PHOTOS_BACKUP" --year 2024 --apply
.EXAMPLE
.\_restructure_archive.ps1 "d:\__PHOTOS_BACKUP" --year ALL --apply
.EXAMPLE
.\_restructure_archive.ps1 "\\NAS\PhotoBackup" --year 2024 --apply
.EXAMPLE
.\_restructure_archive.ps1 --list-to-split

.NOTES
Double-clicking a .ps1 opens it in an editor rather than running it, and an
unsigned script is blocked under the default execution policy. To run this
from a shortcut or the Run box:

    powershell -NoProfile -ExecutionPolicy Bypass -File "<path>\_restructure_archive.ps1" --apply

Add -NoPause to skip the "press a key" at the end; it is skipped automatically
when there is no console to press a key at.
#>

# Deliberately no param() block. Every argument then lands in $args verbatim,
# including the tool's own "--"-prefixed switches, which PowerShell would
# otherwise try to bind to parameters of this script and reject.

Set-Location -LiteralPath $PSScriptRoot

# PowerShell splits an unquoted "1,3" into an array before the script ever
# sees it, and splatting an array to a native command passes each element as
# its own argument -- so "--steps 1,3" would reach the tool as "--steps 1" plus
# a stray "3", which argparse would quietly take for the target path. Joining
# it back up makes the PowerShell form behave exactly like the cmd one.
$toolArgs = @()
$noPause = $false
foreach ($argument in $args) {
    if ($argument -is [string] -and
        ($argument -eq '-NoPause' -or $argument -eq '--no-pause')) {
        $noPause = $true
        continue
    }
    if ($argument -is [array]) {
        $toolArgs += (($argument | ForEach-Object { "$_" }) -join ',')
    }
    else {
        $toolArgs += "$argument"
    }
}

# The tool is stdlib-only by design - a maintenance tool has to run when the
# project's environment does not. Poetry's interpreter is preferred when it is
# there, so a run uses the same Python as the pipeline; a bare "python" is a
# perfectly good fallback.
$command = 'python'
$prefix = @()
if (Get-Command poetry -ErrorAction SilentlyContinue) {
    $command = 'poetry'
    $prefix = @('run', 'python')
}
elseif (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host '[ERROR] Neither poetry nor python is on PATH.' -ForegroundColor Red
    exit 2
}

# Called through the call operator with stdout and stdin left alone, so the
# tool still sees a terminal: that is what its colour output and its typed
# confirmation both depend on.
& $command @prefix 'tools\restructure_archive.py' @toolArgs
$exitCode = $LASTEXITCODE

Write-Host ''
switch ($exitCode) {
    0 { Write-Host 'Nothing left to do.' -ForegroundColor Green }
    1 { Write-Host 'Finished - changes are still pending, or a step reported failures.' -ForegroundColor Yellow }
    default { Write-Host "[ERROR] Restructure stopped with code $exitCode." -ForegroundColor Red }
}
Write-Host ''

# Pause only where there is somebody to pause for: run from a scheduled task or
# a pipeline, a script waiting on a keypress never returns.
if (-not $noPause -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
    Write-Host 'Press any key to continue . . . ' -NoNewline
    $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
    Write-Host ''
}

exit $exitCode
