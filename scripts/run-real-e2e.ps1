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
    $frontendReady = $false
    do {
        try {
            $frontendReady = (Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -TimeoutSec 5).StatusCode -eq 200
            if ($frontendReady) {
                break
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)

    if (-not $frontendReady) {
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
