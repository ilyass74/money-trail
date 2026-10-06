$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker est introuvable. Ouvrir ou installer Docker Desktop puis relancer.'
    }
    $dockerOs = & docker info --format '{{.OSType}}' 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw 'Le moteur Docker ne repond pas. Demarrer Docker Desktop puis relancer.'
    }
    if ($dockerOs.Trim() -ne 'linux') {
        throw 'Ce projet utilise des conteneurs Linux. Activer ce mode dans Docker Desktop.'
    }
    $composeVersion = & docker compose version --short
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Compose est indisponible. Verifier Docker Desktop.'
    }
    $versionText = ($composeVersion.Trim() -replace '^v', '') -replace '-.*$', ''
    if ([version]$versionText -lt [version]'2.20.0') {
        throw 'Docker Compose 2.20 ou plus recent est requis pour ces commandes.'
    }

    $envPath = Join-Path $projectRoot '.env'
    if (-not (Test-Path -LiteralPath $envPath)) {
        $bytes = New-Object byte[] 32
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $password = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
        $template = [IO.File]::ReadAllText((Join-Path $projectRoot '.env.example'))
        $content = $template.Replace('__GENERATE_ME__', $password)
        [IO.File]::WriteAllText($envPath, $content, [Text.UTF8Encoding]::new($false))
        Write-Host 'Configuration locale creee. Le mot de passe est conserve dans .env.'
    } else {
        $content = [IO.File]::ReadAllText($envPath)
        if ($content.Contains('__GENERATE_ME__') -or
            $content -notmatch '(?m)^POSTGRES_PASSWORD=\S+\s*$') {
            throw 'Le fichier .env existe mais son mot de passe est absent ou non configure.'
        }
        Write-Host 'Configuration locale existante conservee.'
    }

    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw 'La configuration Compose est invalide. Corriger le message affiche avant de continuer.'
    }
    $reportsPath = Join-Path $projectRoot 'reports'
    New-Item -ItemType Directory -Path $reportsPath -Force | Out-Null
    $report = [ordered]@{
        checked_at_utc = [DateTime]::UtcNow.ToString('o')
        containers = $dockerOs.Trim()
        compose = $composeVersion.Trim()
        compose_config_valid = $true
        database_started = $false
    }
    [IO.File]::WriteAllText(
        (Join-Path $reportsPath 'windows_preparation.json'),
        ($report | ConvertTo-Json),
        [Text.UTF8Encoding]::new($false)
    )
    Write-Host 'PREPARATION OK - lancer ensuite docker compose up -d --wait postgres'
} finally {
    Pop-Location
}
