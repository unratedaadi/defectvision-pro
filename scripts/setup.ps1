$ErrorActionPreference = 'Stop'

function Invoke-Checked([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command"
    }
}

Push-Location (Join-Path $PSScriptRoot '..')
try {
    if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
    if (-not (Test-Path 'frontend/.env')) {
        Copy-Item 'frontend/.env.example' 'frontend/.env'
    }
    Push-Location backend
    try {
        Invoke-Checked { uv sync --locked --python 3.11 }
        Invoke-Checked { uv run --locked alembic upgrade head }
    } finally {
        Pop-Location
    }
    Invoke-Checked { npm.cmd --prefix frontend ci }
} finally {
    Pop-Location
}
