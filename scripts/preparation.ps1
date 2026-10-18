$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # без этого Invoke-WebRequest в PS 5.1 качает в разы медленнее

# Зависимости для platform/up.sh (kind, Traefik, MLflow, Airflow, RustFS, Prometheus/Grafana)
# и Python-окружение проекта (uv sync, DVC). Git for Windows скриптом не ставится: он должен быть установлен заранее.
# Запуск из корня репозитория:
#   powershell -ExecutionPolicy Bypass -File .\scripts\post-create.ps1
# Сам up.sh запускать из Git Bash:  bash platform/up.sh

$KIND_VERSION = "v0.33.0"
$TOOLS_DIR = Join-Path $env:LOCALAPPDATA "Programs\k8s-tools"
# Список должен совпадать со списком образов в platform/up.sh
$IMAGES = @(
    "apache/airflow:3.3.2",
    "ghcr.io/mlflow/mlflow:v3.16.1",
    "rustfs/rustfs:1.0.0"
)

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# Запускает нативную команду молча и возвращает $true, если код выхода 0.
# Внутри ErrorActionPreference=Continue, иначе stderr от docker при "Stop" может убить скрипт.
function Test-NativeOk {
    param([Parameter(Mandatory = $true)][scriptblock]$Command)
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command *> $null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $old
    }
}

function Refresh-Path {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $env:Path = "$machinePath;$userPath"

    # Каталоги, куда ставится uv (его установщик сам правит пользовательский PATH,
    # но в текущей сессии он ещё не виден).
    $extraPaths = @(
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".cargo\bin")
    )
    foreach ($path in $extraPaths) {
        if ((Test-Path $path) -and (($env:Path -split ";") -notcontains $path)) {
            $env:Path = "$path;$env:Path"
        }
    }
}

# Сохраняет каталог в пользовательский PATH навсегда (иначе kind/kubectl пропадут в новом окне).
function Add-ToUserPath {
    param([Parameter(Mandatory = $true)][string]$Dir)
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if ($userPath) { $parts = @($userPath -split ";" | Where-Object { $_ }) }
    if ($parts -notcontains $Dir) {
        [Environment]::SetEnvironmentVariable("Path", (($parts + $Dir) -join ";"), "User")
        Write-Host "Добавил '$Dir' в пользовательский PATH (подействует в новых окнах терминала)." -ForegroundColor Yellow
    }
}

function Install-WingetPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$DisplayName
    )
    if (-not (Test-Command "winget")) {
        throw "winget не найден. Установите '$DisplayName' вручную и запустите скрипт повторно."
    }
    Write-Host "Устанавливаю $DisplayName ($Id)..." -ForegroundColor Cyan
    winget install --id $Id --exact --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось установить $DisplayName через winget (код $LASTEXITCODE)."
    }
    Refresh-Path
}

function Download-File {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    $parent = Split-Path -Parent $Destination
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Write-Host "Скачиваю $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Destination
}

Write-Host "`n=== Проверка платформы ===" -ForegroundColor Cyan
if ($env:OS -ne "Windows_NT") { throw "Этот скрипт предназначен для Windows PowerShell." }
if (-not [Environment]::Is64BitOperatingSystem) { throw "Поддерживается только 64-битная Windows." }
Refresh-Path

# Git for Windows нужен не сам по себе, а как источник bash, curl, grep, seq, mktemp для up.sh.
Write-Host "`n=== Git for Windows (bash для up.sh) ===" -ForegroundColor Cyan
if (-not (Test-Command "git")) {
    throw "Git for Windows не найден. Установите его вручную (нужен Git Bash для up.sh) и запустите скрипт повторно."
}
$gitRoot = Split-Path (Split-Path (Get-Command git).Source -Parent) -Parent
$gitBash = Join-Path $gitRoot "bin\bash.exe"
if (-not (Test-Path $gitBash)) {
    throw "Не найден Git Bash ('$gitBash'). Переустановите Git for Windows с компонентом Git Bash."
}
Write-Host "Git Bash: $gitBash" -ForegroundColor Green

# up.sh использует curl --aws-sigv4 (нужен curl 7.75+)
$curlLine = & $gitBash -c "curl --version" | Select-Object -First 1
if ($curlLine -match "curl (\d+)\.(\d+)") {
    if ([version]"$($Matches[1]).$($Matches[2])" -lt [version]"7.75") {
        throw "curl в Git Bash слишком старый ($curlLine): нужен 7.75+ для --aws-sigv4. Обновите Git for Windows."
    }
    Write-Host "curl: $curlLine" -ForegroundColor Green
} else {
    throw "Не удалось определить версию curl в Git Bash."
}

Write-Host "`n=== uv ===" -ForegroundColor Cyan
if (Test-Command "uv") {
    Write-Host "uv уже установлен: $(uv --version)" -ForegroundColor Green
} else {
    Write-Host "Устанавливаю uv..." -ForegroundColor Cyan
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    Refresh-Path
    if (-not (Test-Command "uv")) {
        throw "uv установщик завершился, но uv не найден в PATH. Перезапустите PowerShell и повторите запуск."
    }
    Write-Host "$(uv --version)" -ForegroundColor Green
}

Write-Host "`n=== kind ===" -ForegroundColor Cyan
if (Test-Command "kind") {
    Write-Host "kind уже установлен: $(kind version)" -ForegroundColor Green
} else {
    # В PATH kind нет: скачиваем (если ещё не скачан) и только теперь сохраняем каталог в PATH.
    $destination = Join-Path $TOOLS_DIR "kind.exe"
    if (-not (Test-Path $destination)) {
        Download-File -Url "https://kind.sigs.k8s.io/dl/$KIND_VERSION/kind-windows-amd64" -Destination $destination
    }
    Add-ToUserPath $TOOLS_DIR
    Refresh-Path
    if (-not (Test-Command "kind")) { throw "kind скачан в '$destination', но не найден в PATH." }
    Write-Host "Установлен $(kind version)" -ForegroundColor Green
}

Write-Host "`n=== kubectl ===" -ForegroundColor Cyan
if (Test-Command "kubectl") {
    Write-Host "kubectl уже установлен." -ForegroundColor Green
} else {
    # В PATH kubectl нет: скачиваем (если ещё не скачан) и только теперь сохраняем каталог в PATH.
    $binary = Join-Path $TOOLS_DIR "kubectl.exe"
    if (-not (Test-Path $binary)) {
        $version = (Invoke-RestMethod "https://dl.k8s.io/release/stable.txt").Trim()
        $checksumFile = Join-Path $env:TEMP "kubectl.sha256"

        Download-File -Url "https://dl.k8s.io/release/$version/bin/windows/amd64/kubectl.exe" -Destination $binary
        Download-File -Url "https://dl.k8s.io/release/$version/bin/windows/amd64/kubectl.exe.sha256" -Destination $checksumFile

        $expected = (Get-Content $checksumFile -Raw).Trim().ToLowerInvariant()
        $actual = (Get-FileHash -Path $binary -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            Remove-Item $binary -Force -ErrorAction SilentlyContinue
            throw "Проверка SHA256 для kubectl не пройдена."
        }
    }

    Add-ToUserPath $TOOLS_DIR
    Refresh-Path
    if (-not (Test-Command "kubectl")) { throw "kubectl скачан в '$binary', но не найден в PATH." }
    Write-Host "kubectl установлен: $binary" -ForegroundColor Green
}

Write-Host "`n=== Helm ===" -ForegroundColor Cyan
if (-not (Test-Command "helm")) {
    Install-WingetPackage -Id "Helm.Helm" -DisplayName "Helm"
    if (-not (Test-Command "helm")) {
        throw "Helm установлен, но не найден в PATH. Перезапустите PowerShell и повторите запуск."
    }
}
Write-Host "$(helm version --short)" -ForegroundColor Green

Write-Host "`n=== Docker Desktop ===" -ForegroundColor Cyan
if (-not (Test-Command "docker")) {
    throw "Команда docker не найдена. Установите Docker Desktop (WSL2-бэкенд) и перезапустите PowerShell."
}
if (-not (Test-NativeOk { docker info })) {
    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktop) {
        Write-Host "Запускаю Docker Desktop..." -ForegroundColor Yellow
        Start-Process -FilePath $dockerDesktop
    }
    $dockerReady = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 2
        if (Test-NativeOk { docker info }) { $dockerReady = $true; break }
    }
    if (-not $dockerReady) {
        throw "Docker Engine не запустился за 120 секунд. Дождитесь статуса Running в Docker Desktop и запустите скрипт снова."
    }
}
Write-Host "Docker Engine доступен." -ForegroundColor Green

Write-Host "`n=== Зависимости Python ===" -ForegroundColor Cyan
if (Test-Path "pyproject.toml") {
    uv sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync завершился с ошибкой." }

    Write-Host "Версия DVC из окружения проекта:" -ForegroundColor Cyan
    uv run dvc --version
    if ($LASTEXITCODE -ne 0) {
        throw "DVC недоступен. Проверьте, что dvc[s3] указан в зависимостях pyproject.toml."
    }
} else {
    Write-Host "pyproject.toml не найден в текущем каталоге. Пропускаю uv sync и проверку DVC." -ForegroundColor Yellow
    Write-Host "Запустите скрипт из корня репозитория." -ForegroundColor Yellow
}

Write-Host "`n=== Репозитории Helm ===" -ForegroundColor Cyan
# up.sh сам делает 'helm repo add', но без обновления индекса: при устаревшем индексе
# закреплённые версии чартов (--version) могут не найтись. Поэтому обновляем здесь.
helm repo add traefik https://traefik.github.io/charts --force-update
if ($LASTEXITCODE -ne 0) { throw "Не удалось добавить Helm-репозиторий traefik." }
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
if ($LASTEXITCODE -ne 0) { throw "Не удалось добавить Helm-репозиторий prometheus-community." }
helm repo update
if ($LASTEXITCODE -ne 0) { throw "Не удалось обновить Helm-репозитории." }

Write-Host "`n=== Docker-образы ===" -ForegroundColor Cyan
foreach ($image in $IMAGES) {
    if (Test-NativeOk { docker image inspect $image }) {
        Write-Host "Образ уже есть локально: $image" -ForegroundColor Green
        continue
    }
    Write-Host "Скачиваю образ $image..." -ForegroundColor Cyan
    docker pull $image
    if ($LASTEXITCODE -ne 0) { throw "Не удалось скачать Docker-образ '$image'." }
}

Write-Host "`nГотово. Откройте НОВОЕ окно терминала (чтобы подхватился PATH) и запустите платформу из Git Bash:" -ForegroundColor Green
Write-Host "  & S3_KEY=... S3_SECRET=... `"$gitBash`" platform/up.sh" -ForegroundColor Green