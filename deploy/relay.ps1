# Home relay: fetch the sources that block the cloud server and upload them to it over Tailscale.
# Runs from Windows Task Scheduler (daily, and at logon); harmless when the server or the source is unreachable.
$ErrorActionPreference = "SilentlyContinue"
$server = "https://srv1.tailf3b6bc.ts.net/api/v1/admin/relay"
$log = "D:\pharmacopy\tmp\relay.log"
$ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
try {
    $sources = Invoke-RestMethod -Uri $server -TimeoutSec 30
} catch {
    Add-Content $log "$(Get-Date -Format s) server unreachable"; exit 0
}
foreach ($p in $sources.PSObject.Properties) {
    try {
        $page = Invoke-WebRequest -Uri $p.Value -UserAgent $ua -UseBasicParsing -TimeoutSec 60
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($page.Content)
        $r = Invoke-RestMethod -Method Post -Uri "$server/$($p.Name)" -Body $bytes -ContentType "text/html; charset=utf-8" -TimeoutSec 60
        Add-Content $log "$(Get-Date -Format s) $($p.Name) ok $($r.bytes) bytes"
    } catch {
        Add-Content $log "$(Get-Date -Format s) $($p.Name) failed: $($_.Exception.Message)"
    }
}
