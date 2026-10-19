<#
.SYNOPSIS
    Point d'entrée des tâches du projet (remplace make sous Windows).
.EXAMPLE
    .\tasks.ps1 setup | test | lint | run | report | airflow-up | airflow-down | secrets
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("setup", "test", "lint", "run", "report", "airflow-up", "airflow-down", "secrets", "help")]
    [string]$Target = "help"
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $Logs | Out-Null

function Use-Venv {
    if (-not (Test-Path $Py)) { throw "Venv absent : lancez d'abord .\tasks.ps1 setup" }
    . (Join-Path $Venv "Scripts\Activate.ps1")
}

switch ($Target) {
    "setup" {
        if (-not (Test-Path $Py)) {
            py -3.11 -m venv $Venv
            if ($LASTEXITCODE -ne 0) { throw "Création du venv impossible (Python 3.11 requis)" }
        }
        Use-Venv
        & $Py -m pip install --upgrade pip *> (Join-Path $Logs "pip_upgrade.log")
        & $Py -m pip install -e ".[dev]" *> (Join-Path $Logs "pip_install.log")
        if ($LASTEXITCODE -ne 0) { throw "pip install a échoué, voir logs\pip_install.log" }
        Write-Host "Setup OK"
    }
    "test" {
        Use-Venv
        & $Py -m pytest
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $Py -m ruff check src tests dags
        exit $LASTEXITCODE
    }
    "lint" {
        Use-Venv
        & $Py -m ruff check src tests dags
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $Py -m ruff format --check src tests dags
        exit $LASTEXITCODE
    }
    "run" {
        Use-Venv
        & $Py -m maamora.cli all
        exit $LASTEXITCODE
    }
    "report" {
        Use-Venv
        & $Py -m maamora.cli report
        exit $LASTEXITCODE
    }
    "secrets" {
        Use-Venv
        $files = git -C $Root ls-files
        & (Join-Path $Venv "Scripts\detect-secrets.exe") scan @files
        exit $LASTEXITCODE
    }
    "airflow-up" {
        docker compose -f (Join-Path $Root "docker-compose.yml") up -d
        exit $LASTEXITCODE
    }
    "airflow-down" {
        docker compose -f (Join-Path $Root "docker-compose.yml") down
        exit $LASTEXITCODE
    }
    default {
        Write-Host "Usage : .\tasks.ps1 <setup|test|lint|run|report|airflow-up|airflow-down|secrets>"
    }
}
