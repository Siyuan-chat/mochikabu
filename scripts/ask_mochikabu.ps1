[CmdletBinding()]
param(
    [Parameter(Mandatory, Position=0)][string]$Question,
    [string]$SkillRoot = (Split-Path $PSScriptRoot -Parent),
    [switch]$Json
)
$ErrorActionPreference = 'Stop'
$entry = (Resolve-Path -LiteralPath (Join-Path $SkillRoot 'SKILL.md')).Path
$instructions = [IO.File]::ReadAllText($entry)
if ($instructions -notmatch '(?m)^name: mochikabu\s*$') {
    throw "Expected the installed mochikabu skill at $entry"
}
# Use UTF-8 stdin so quotes, spaces and Japanese text survive Windows argument parsing.
$instructions += [Environment]::NewLine + [IO.File]::ReadAllText((Join-Path $SkillRoot 'workflow.md'))
$inputText = @"
Apply the following installed skill to the user question below. Resolve relative helper paths from $entry.

<installed_skill>
$instructions
</installed_skill>

<user_question>
$Question
</user_question>
"@
$OutputEncoding = [Text.UTF8Encoding]::new($false)
$options = @('--search','exec','--skip-git-repo-check','--ephemeral','--sandbox','workspace-write')
if ($Json) { $options += '--json' }
$inputText | & codex @options -
exit $LASTEXITCODE
