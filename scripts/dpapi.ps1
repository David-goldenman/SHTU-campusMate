param([ValidateSet('protect', 'unprotect')][string]$Action)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$payload = [Console]::In.ReadToEnd()
if ($Action -eq 'protect') {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    $encrypted = [System.Security.Cryptography.ProtectedData]::Protect($bytes, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    [Console]::Write([Convert]::ToBase64String($encrypted))
} else {
    $bytes = [System.Security.Cryptography.ProtectedData]::Unprotect([Convert]::FromBase64String($payload), $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    [Console]::Write([System.Text.Encoding]::UTF8.GetString($bytes))
}
