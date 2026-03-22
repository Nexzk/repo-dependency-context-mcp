param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Query = "require_admin"
)

$ErrorActionPreference = "Stop"

function Invoke-JsonPost {
    param(
        [string]$Url,
        [hashtable]$Body
    )

    return Invoke-RestMethod -Method Post -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 10)
}

Write-Host "Smoke check: health"
$health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/healthz"
if ($health.status -ne "ok") {
    throw "Health endpoint did not return ok."
}

Write-Host "Smoke check: playground"
$playground = Invoke-WebRequest -Method Get -Uri "$BaseUrl/playground"
if ($playground.StatusCode -ne 200) {
    throw "Playground endpoint did not return 200."
}

Write-Host "Smoke check: metrics"
$metrics = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/observability/metrics"
if ($null -eq $metrics.query_logs) {
    throw "Metrics payload is missing query_logs."
}

Write-Host "Smoke check: query search"
if (-not $env:RDCMCP_SMOKE_TENANT_ID -or -not $env:RDCMCP_SMOKE_REPO_ID) {
    Write-Warning "Skipping /api/query/search because RDCMCP_SMOKE_TENANT_ID or RDCMCP_SMOKE_REPO_ID is not set."
}
else {
    $search = Invoke-JsonPost -Url "$BaseUrl/api/query/search" -Body @{
        tenant_id = $env:RDCMCP_SMOKE_TENANT_ID
        repo_id = $env:RDCMCP_SMOKE_REPO_ID
        query = $Query
        task_type = "locate"
        top_k = 3
    }

    if ($null -eq $search.evidence) {
        throw "Search response is missing evidence."
    }
}

Write-Host "Smoke check complete."
