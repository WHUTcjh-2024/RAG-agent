$ErrorActionPreference = "Stop"

if (-not $env:AGENT_INTERNAL_TOKEN) {
    # Only scoped to this process; it does not modify the developer's .env file.
    $env:AGENT_INTERNAL_TOKEN = "atelier-real-e2e-local-token"
}

try {
    docker compose up --build -d
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose startup failed."
    }

    $deadline = (Get-Date).AddMinutes(3)
    $health = $null
    do {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:18000/health" -TimeoutSec 5
            $javaReady = (Invoke-WebRequest -Uri "http://127.0.0.1:8080/actuator/health" -TimeoutSec 5).StatusCode -eq 200
            $frontendReady = (Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -TimeoutSec 5).StatusCode -eq 200
            if ($health.status -in @("ready", "degraded") -and $javaReady -and $frontendReady) {
                break
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)

    if ($null -eq $health -or $health.status -notin @("ready", "degraded") -or -not $javaReady -or -not $frontendReady) {
        throw "Full stack did not become ready within three minutes."
    }

    Push-Location frontend
    try {
        npm run test:e2e:real
    }
    finally {
        Pop-Location
    }
}
finally {
    docker compose down --volumes
}
