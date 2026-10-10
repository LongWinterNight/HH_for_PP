# ============================================================
# BaseVacancy — запуск для внешнего доступа
# ============================================================
# Поднимает приложение так, чтобы оно было видно из интернета
# по белому IP через проброшенный на роутере порт 8000.
#
# Запуск:  powershell -ExecutionPolicy Bypass -File scripts\serve.ps1
#
# Пока окно открыто — сайт доступен. Закрыли окно или выключили
# компьютер — сайт пропал: приложение живёт здесь, а не на сервере.
# ============================================================

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# Интерфейс собирается заранее: FastAPI раздаёт готовую сборку,
# а не исходники. Без dist приложение честно скажет, что не собрано,
# но лучше не доводить до этого.
if (-not (Test-Path "frontend\dist\index.html")) {
    Write-Host "Интерфейс не собран — собираю..." -ForegroundColor Yellow
    Push-Location frontend
    npm install
    npm run build
    Pop-Location
}

# Проверка защиты. Открывать приложение наружу без пароля нельзя:
# любой, кто найдёт адрес, сможет запустить сбор с перезаписью базы.
$envFile = Join-Path $projectRoot ".env"
$hasAuth = $false
if (Test-Path $envFile) {
    $content = Get-Content $envFile -Raw
    $hasAuth = ($content -match 'BASIC_AUTH_USER=\S') -and ($content -match 'BASIC_AUTH_PASSWORD=\S')
}

if (-not $hasAuth) {
    Write-Host ""
    Write-Host "ВНИМАНИЕ: BASIC_AUTH_USER и BASIC_AUTH_PASSWORD не заданы в .env" -ForegroundColor Red
    Write-Host "Приложение будет открыто всем, кто знает адрес." -ForegroundColor Red
    $answer = Read-Host "Продолжить без пароля? (нет/да)"
    if ($answer -ne 'да') { exit 1 }
}

# Резервная копия базы перед открытием доступа: сбор с выключенным
# дописыванием стирает таблицу целиком, и тестировщик может это сделать.
$db = Join-Path $projectRoot "data\hh_vacancies.db"
if (Test-Path $db) {
    $backupDir = Join-Path $projectRoot "data\backups"
    if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }

    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    Copy-Item $db (Join-Path $backupDir "hh_vacancies.db.$stamp")
    Write-Host "Копия базы: data\backups\hh_vacancies.db.$stamp" -ForegroundColor DarkGray

    # Держим последние десять копий: база весит около мегабайта, но
    # за месяц ежедневных запусков папка распухнет без всякой пользы.
    Get-ChildItem $backupDir -Filter "hh_vacancies.db.*" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 10 |
        Remove-Item -Force
}

Write-Host ""
Write-Host "BaseVacancy запускается" -ForegroundColor Green
Write-Host "  локально:        http://127.0.0.1:8000"

# Адреса не записаны в файле: репозиторий публичный, а домашний адрес с
# открытым портом в нём — приглашение. Адрес в сети определяется на
# месте, внешний берётся из PUBLIC_URL в .env, если он там задан.
$lan = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown" } |
    Select-Object -First 1 -ExpandProperty IPAddress
if ($lan) { Write-Host "  в вашей сети:    http://${lan}:8000" }

$envFile = Join-Path $projectRoot ".env"
$publicUrl = $null
if (Test-Path $envFile) {
    $line = Get-Content $envFile | Where-Object { $_ -match "^PUBLIC_URL=(.+)$" } | Select-Object -First 1
    if ($line) { $publicUrl = ($line -replace "^PUBLIC_URL=", "").Trim() }
}
if ($publicUrl) { Write-Host "  из интернета:    $publicUrl" }
Write-Host ""
Write-Host "Остановить: Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

# Через надзор, а не напрямую: он подхватывает правки в коде без ручного
# перезапуска, но ждёт, пока сервер освободится — не обрывает идущий сбор
# и не роняет страницу под руками у того, кто на неё смотрит.
# host 0.0.0.0 — слушать все интерфейсы, иначе снаружи не достучаться.
python scripts\serve.py --хост 0.0.0.0 --порт 8000
