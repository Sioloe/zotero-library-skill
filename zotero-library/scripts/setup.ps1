param([string]$ConfigPath = (Join-Path $env:LOCALAPPDATA 'ZoteroCodex\config.json'))
$ErrorActionPreference = 'Stop'
$taskType = Read-Host 'Library type: user or group (default user)'
if (-not $taskType) { $taskType = 'user' }
$taskType = $taskType.Trim().ToLowerInvariant()
if ($taskType -notin @('user','group')) { throw 'Library type must be user or group.' }
$taskId = Read-Host 'Numeric Zotero User ID or Group ID'
$taskId = $taskId.Trim()
if ($taskId -notmatch '^[1-9][0-9]*$') { throw 'Please use a positive numeric library ID, not a username.' }
$taskSecret = Read-Host 'Zotero API key (hidden input)' -AsSecureString
if ($taskSecret.Length -eq 0) { throw 'API key cannot be empty.' }
$taskConfig = [ordered]@{
    library_type = $taskType
    library_id = $taskId
    protected_api_key = (ConvertFrom-SecureString -SecureString $taskSecret)
}
$taskParent = Split-Path -Parent ([IO.Path]::GetFullPath($ConfigPath))
New-Item -ItemType Directory -Force -Path $taskParent | Out-Null
$taskConfig | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
Write-Output "Saved encrypted Zotero configuration: $ConfigPath"
Write-Output 'Ask Codex to run the zotero-library status check. Do not share the API key in chat.'
