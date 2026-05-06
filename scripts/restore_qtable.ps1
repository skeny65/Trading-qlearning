# restore_qtable.ps1 - Restaura la Q-Table desde un backup
# Uso: .\scripts\restore_qtable.ps1 -BackupFile "data\qlearning\backups\q_table_20260503_120000.json"

param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile
)

$target = "data\qlearning\q_table.json"

if (-not (Test-Path $BackupFile)) {
    Write-Host "ERROR: Backup no encontrado: $BackupFile" -ForegroundColor Red
    exit 1
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
if (Test-Path $target) {
    Copy-Item $target "data\qlearning\q_table_pre_restore_$ts.json"
    Write-Host "Backup previo guardado como q_table_pre_restore_$ts.json" -ForegroundColor Yellow
}

Copy-Item $BackupFile $target
Write-Host "Q-Table restaurada desde: $BackupFile" -ForegroundColor Green
Write-Host "Reinicia el bot para cargar la nueva Q-Table." -ForegroundColor Cyan
