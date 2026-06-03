param(
    [ValidateSet("start", "stop", "restart", "status", "logs")]
    [string]$Command = "start",
    [switch]$IncludeOllama
)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$VenvPath = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$RuntimeDir = Join-Path $Root ".runtime"
$StateFile = Join-Path $RuntimeDir "services.json"
$LogsDir = Join-Path $Root "logs"
$ApiUrl = "http://localhost:8000/api/status"
$UiUrl = "http://localhost:5173"
$OllamaUrl = "http://localhost:11434/api/tags"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Read-ServiceState {
    $state = @{}
    if (Test-Path $StateFile) {
        $json = Get-Content $StateFile -Raw | ConvertFrom-Json
        foreach ($property in $json.PSObject.Properties) {
            $state[$property.Name] = [int]$property.Value
        }
    }
    return $state
}

function Write-ServiceState {
    param([hashtable]$State)
    Ensure-Directory $RuntimeDir
    $State | ConvertTo-Json | Set-Content -Path $StateFile -Encoding UTF8
}

function Get-BasePython {
    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $bundledPython) {
        return @{ Exe = $bundledPython; Args = @() }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Exe = $python.Source; Args = @() }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Exe = $py.Source; Args = @("-3") }
    }

    throw "Python was not found. Install Python 3.11+ or run this from Codex with the bundled runtime available."
}

function Ensure-PythonEnvironment {
    if (-not (Test-Path $VenvPython)) {
        Write-Step "Creating Python virtual environment"
        $basePython = Get-BasePython
        & $basePython.Exe @($basePython.Args + @("-m", "venv", $VenvPath))
    }

    & $VenvPython -c "import flask, flask_cors, langchain_ollama, pytest" *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Step "Installing Python dependencies"
        & $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
    }
}

function Test-Http {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode
    } catch {
        return $null
    }
}

function Wait-Http {
    param(
        [string]$Url,
        [int]$Seconds = 25
    )

    for ($i = 0; $i -lt $Seconds; $i++) {
        $statusCode = Test-Http $Url
        if ($statusCode) {
            return $statusCode
        }
        Start-Sleep -Seconds 1
    }
    return $null
}

function Get-PortProcessIds {
    param([int]$Port)
    $processIds = @()
    try {
        $processIds = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        $processIds = @()
    }

    if ($processIds.Count -eq 0) {
        $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
        foreach ($line in (& netstat -ano)) {
            if ($line -match $pattern) {
                $processIds += [int]$matches[1]
            }
        }
    }

    return @($processIds | Select-Object -Unique)
}

function Stop-Pid {
    param([int]$ProcessId)
    if ($ProcessId -gt 0 -and (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
        Write-Step "Stopping process $ProcessId"
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Stop-Port {
    param([int]$Port)
    $processIds = @(Get-PortProcessIds $Port)
    foreach ($processId in $processIds) {
        Stop-Pid $processId
    }
}

function Format-CmdArgument {
    param([string]$Value)
    if ($Value -match '[\s&()^|<>"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

function Start-DetachedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    Ensure-Directory $LogsDir
    $stdoutLog = Join-Path $LogsDir "$Name.out.log"
    $stderrLog = Join-Path $LogsDir "$Name.err.log"
    $argumentLine = ($Arguments | ForEach-Object { Format-CmdArgument $_ }) -join " "
    $commandLine = "cd /d $(Format-CmdArgument $WorkingDirectory) && $(Format-CmdArgument $FilePath) $argumentLine >> $(Format-CmdArgument $stdoutLog) 2>> $(Format-CmdArgument $stderrLog)"

    $process = Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/c", $commandLine) `
        -WindowStyle Hidden `
        -PassThru

    $state = Read-ServiceState
    $state[$Name] = $process.Id
    Write-ServiceState $state
    return $process.Id
}

function Resolve-Ollama {
    $command = Get-Command ollama -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $local = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $local) {
        return $local
    }

    return $null
}

function Ensure-Ollama {
    if (Test-Http $OllamaUrl) {
        Write-Step "Ollama is already running"
        return
    }

    $ollama = Resolve-Ollama
    if (-not $ollama) {
        Write-Warning "Ollama was not found. Start Ollama manually before running pipelines."
        return
    }

    Write-Step "Starting Ollama"
    Start-DetachedProcess -Name "ollama" -FilePath $ollama -Arguments @("serve") -WorkingDirectory $Root | Out-Null
    if (-not (Wait-Http $OllamaUrl 20)) {
        Write-Warning "Ollama did not answer on port 11434."
    }
}

function Show-ModelStatus {
    try {
        $payload = Invoke-WebRequest -Uri $OllamaUrl -UseBasicParsing -TimeoutSec 5 | ConvertFrom-Json
        $models = @($payload.models | ForEach-Object { $_.name })
        foreach ($requiredModel in @("mistral:7b", "qwen2.5-coder:7b")) {
            if ($models -notcontains $requiredModel) {
                Write-Warning "Missing Ollama model: $requiredModel"
            }
        }
    } catch {
        Write-Warning "Could not inspect Ollama models."
    }
}

function Start-Stack {
    Ensure-Directory $LogsDir
    Ensure-PythonEnvironment
    Ensure-Ollama
    Show-ModelStatus

    if (-not (Test-Http $ApiUrl)) {
        Write-Step "Starting backend API on http://localhost:8000"
        Start-DetachedProcess -Name "backend" -FilePath $VenvPython -Arguments @("api\server.py") -WorkingDirectory $Root | Out-Null
        Wait-Http $ApiUrl 30 | Out-Null
    } else {
        Write-Step "Backend API is already running"
    }

    if (-not (Test-Http $UiUrl)) {
        Write-Step "Starting UI on http://localhost:5173"
        Start-DetachedProcess -Name "ui" -FilePath $VenvPython -Arguments @("-m", "http.server", "5173", "--directory", "ui") -WorkingDirectory $Root | Out-Null
        Wait-Http $UiUrl 20 | Out-Null
    } else {
        Write-Step "UI is already running"
    }

    Show-Status
}

function Stop-Stack {
    $state = Read-ServiceState

    foreach ($service in @("backend", "ui")) {
        if ($state.ContainsKey($service)) {
            Stop-Pid $state[$service]
            $state.Remove($service)
        }
    }

    Stop-Port 8000
    Stop-Port 5173

    if ($IncludeOllama -and $state.ContainsKey("ollama")) {
        Stop-Pid $state["ollama"]
        $state.Remove("ollama")
    }

    Write-ServiceState $state
    Write-Step "Stopped project services"
}

function Show-Status {
    $apiStatus = Test-Http $ApiUrl
    $uiStatus = Test-Http $UiUrl
    $ollamaStatus = Test-Http $OllamaUrl

    Write-Host ""
    Write-Host "Service status"
    Write-Host "--------------"
    Write-Host ("Backend API : {0}" -f ($(if ($apiStatus) { "online ($apiStatus) http://localhost:8000" } else { "offline" })))
    Write-Host ("UI          : {0}" -f ($(if ($uiStatus) { "online ($uiStatus) http://localhost:5173" } else { "offline" })))
    Write-Host ("Ollama      : {0}" -f ($(if ($ollamaStatus) { "online ($ollamaStatus) http://localhost:11434" } else { "offline" })))
    Write-Host ""
}

function Show-Logs {
    Get-ChildItem -Path $LogsDir -Filter "*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object Name, LastWriteTime, Length
}

switch ($Command) {
    "start" { Start-Stack }
    "stop" { Stop-Stack }
    "restart" {
        Stop-Stack
        Start-Sleep -Seconds 2
        Start-Stack
    }
    "status" { Show-Status }
    "logs" { Show-Logs }
}
