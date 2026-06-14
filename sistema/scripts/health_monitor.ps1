param([int]$Port = 8001)

$url          = "http://localhost:$Port"
$NGROK_URL    = "https://shaft-goliath-shakable.ngrok-free.dev"
$ESTRATEGIAS  = "C:\Users\kenyb\Desktop\BOT_EJECUTOR\Bot_Ejecutor\estrategias"
$HB_GRID      = "C:\Users\kenyb\Desktop\BOT_EJECUTOR\Bot_Grid\logs\heartbeat.json"
$HB_MANAGER   = "C:\Users\kenyb\Desktop\BOT_EJECUTOR\Bot_Manager\logs\heartbeat.json"
$INTERVAL_SEC = 15

# ── helpers ───────────────────────────────────────────────────────────────────

function Get-AgeSec {
    param([string]$IsoTimestamp)
    try {
        $dt = [datetime]::Parse($IsoTimestamp).ToUniversalTime()
        return [int]([datetime]::UtcNow - $dt).TotalSeconds
    } catch { return 9999 }
}

function Format-Age {
    param([int]$Sec)
    if ($Sec -ge 9999) { return "?" }
    if ($Sec -lt 60)   { return "${Sec}s" }
    if ($Sec -lt 3600) { return "$([math]::Round($Sec / 60, 0))min" }
    return "$([math]::Round($Sec / 3600, 1))h"
}

function Get-AgeColor {
    param([int]$Sec, [int]$Warn = 120, [int]$Error = 300)
    if ($Sec -le $Warn)  { return "Green"  }
    if ($Sec -le $Error) { return "Yellow" }
    return "Red"
}

function Get-CarpetaBalance {
    param([string]$CarpetaId)
    $path = "$ESTRATEGIAS\estrategia_$CarpetaId\actividades\balance.json"
    try {
        if (Test-Path $path) {
            return [math]::Round([double](Get-Content $path -Raw | ConvertFrom-Json).balance, 2)
        }
    } catch {}
    return $null
}

function Get-LastTradeAllCarpetas {
    param([string[]]$Ids)
    $lastTs    = $null
    $lastTrade = $null
    foreach ($id in $Ids) {
        $path = "$ESTRATEGIAS\estrategia_$id\actividades\ejecuciones.jsonl"
        if (-not (Test-Path $path)) { continue }
        $closes = Get-Content $path -Encoding UTF8 -ErrorAction SilentlyContinue |
            Where-Object { $_.Trim() -ne "" } |
            ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } |
            Where-Object { $_ -and $_.tipo -eq "close" }
        $last = $closes | Select-Object -Last 1
        if ($last) {
            $tTs = try { [datetime]$last.ts } catch { $null }
            if ($tTs -and ($null -eq $lastTs -or $tTs -gt $lastTs)) {
                $lastTs    = $tTs
                $lastTrade = $last
            }
        }
    }
    return $lastTrade
}

# ── seccion Carpeta 1 + ngrok ─────────────────────────────────────────────────

function Show-Carpeta1 {
    param([object]$Metrics, [object]$Health)

    Write-Host "   --- Carpeta 1  [TradingView / SOLUSDT] ---" -ForegroundColor DarkCyan

    # Leer config
    $cfgPath = "$ESTRATEGIAS\estrategia_1\config.json"
    try {
        $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
        $enabled    = $cfg.enabled
        $liveTrading = $cfg.binance_live
        $symbol     = if ($cfg.symbols_permitidos.Count -gt 0) { $cfg.symbols_permitidos -join "," } else { "CUALQUIERA" }
    } catch {
        $enabled = $false; $liveTrading = $false; $symbol = "?"
    }

    # Estado carpeta
    $stText  = if ($enabled) { "ACTIVA" } else { "disabled" }
    $stColor = if ($enabled) { "Green"  } else { "DarkGray" }
    Write-Host "   Estado      : " -NoNewline; Write-Host $stText -ForegroundColor $stColor

    # Modo Binance
    $mText  = if ($liveTrading) { "LIVE  *** ORDENES REALES ***" } else { "DRY_RUN" }
    $mColor = if ($liveTrading) { "Red" } else { "Yellow" }
    Write-Host "   Modo        : " -NoNewline; Write-Host $mText -ForegroundColor $mColor

    # Simbolo
    Write-Host "   Simbolo     :  $symbol"

    # Ngrok healthcheck
    $ngrokOk = $false
    try {
        $r = Invoke-WebRequest "$NGROK_URL/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        $ngrokOk = ($r.StatusCode -eq 200)
    } catch { $ngrokOk = $false }

    $ngrokColor = if ($ngrokOk) { "Green" } else { "Red" }
    $ngrokText  = if ($ngrokOk) { "OK  $NGROK_URL" } else { "OFFLINE  $NGROK_URL" }
    Write-Host "   Ngrok       : " -NoNewline; Write-Host $ngrokText -ForegroundColor $ngrokColor

    # Wins / Losses / PnL
    $cf = $null
    if ($Metrics -and $Metrics.carpetas) { try { $cf = $Metrics.carpetas."1" } catch {} }
    if ($cf -and $null -ne $cf.total_trades -and $cf.total_trades -gt 0) {
        $wC   = if ($cf.wins   -gt 0) { "Green"   } else { "DarkGray" }
        $lC   = if ($cf.losses -gt 0) { "Red"     } else { "DarkGray" }
        $pC   = if ([double]$cf.pnl_acumulado -ge 0) { "Green" } else { "Red" }
        Write-Host "   Wins / Loss : " -NoNewline
        Write-Host "$($cf.wins)" -ForegroundColor $wC -NoNewline
        Write-Host " / " -NoNewline
        Write-Host "$($cf.losses)" -ForegroundColor $lC
        Write-Host "   PnL         : " -NoNewline; Write-Host "$($cf.pnl_acumulado)%" -ForegroundColor $pC
    } else {
        Write-Host "   Wins / Loss :  sin trades aun" -ForegroundColor DarkGray
    }

    # Balance
    $bal = Get-CarpetaBalance -CarpetaId "1"
    if ($null -ne $bal) {
        $bC = if ($bal -ge 100) { "Green" } elseif ($bal -ge 90) { "Yellow" } else { "Red" }
        Write-Host "   Balance     : " -NoNewline; Write-Host "$bal USDT" -ForegroundColor $bC
    }

    Write-Host ""
}

# ── seccion Bot Grid  [carpeta 9] ─────────────────────────────────────────────

function Show-BotGrid {
    param([object]$Metrics)
    $carpeta = "9"

    Write-Host "   --- Bot Grid  [carpeta $carpeta] ---" -ForegroundColor DarkCyan

    if (-not (Test-Path $HB_GRID)) {
        Write-Host "   Estado      : " -NoNewline; Write-Host "OFFLINE  (no levantado)" -ForegroundColor Red
        Write-Host ""; return
    }

    try {
        $hb  = Get-Content $HB_GRID -Encoding UTF8 -Raw -ErrorAction Stop | ConvertFrom-Json
        $age = Get-AgeSec -IsoTimestamp $hb.updated_at

        $st = $hb.status.ToUpper()
        $stColor = "Red"
        if     ($st -eq "OK")                     { $stColor = "Green"  }
        elseif ($st -in @("STARTING","DEGRADED")) { $stColor = "Yellow" }

        Write-Host "   Estado      : " -NoNewline
        Write-Host $st -ForegroundColor $stColor -NoNewline
        $ageColor = Get-AgeColor -Sec $age -Warn 90 -Error 180
        Write-Host "  (hace $(Format-Age $age))" -ForegroundColor $ageColor

        $mText  = if ($hb.dry_run -eq $true) { "DRY_RUN" } else { "LIVE  *** ORDENES REALES ***" }
        $mColor = if ($hb.dry_run -eq $true) { "Yellow"  } else { "Red" }
        Write-Host "   Modo        : " -NoNewline; Write-Host $mText -ForegroundColor $mColor

        $wsText  = if ($null -ne $hb.ws_silence_sec) { "$($hb.ws_silence_sec)s" } else { "iniciando" }
        $wsColor = if ($null -eq $hb.ws_silence_sec) { "Yellow" } elseif ($hb.ws_silence_sec -le 30) { "Green" } elseif ($hb.ws_silence_sec -le 90) { "Yellow" } else { "Red" }
        $exText  = if ($hb.executor_alive -eq $true) { "OK" } else { "OFFLINE" }
        $exColor = if ($hb.executor_alive -eq $true) { "Green" } else { "Red" }
        Write-Host "   WS Binance  : " -NoNewline; Write-Host $wsText -ForegroundColor $wsColor -NoNewline
        Write-Host "   Ejecutor: "     -NoNewline; Write-Host $exText -ForegroundColor $exColor

        $cf = $null
        if ($Metrics -and $Metrics.carpetas) { try { $cf = $Metrics.carpetas.$carpeta } catch {} }
        if ($cf -and $null -ne $cf.total_trades -and $cf.total_trades -gt 0) {
            $wC = if ($cf.wins   -gt 0) { "Green"   } else { "DarkGray" }
            $lC = if ($cf.losses -gt 0) { "Red"     } else { "DarkGray" }
            $pC = if ([double]$cf.pnl_acumulado -ge 0) { "Green" } else { "Red" }
            Write-Host "   Wins / Loss : " -NoNewline
            Write-Host "$($cf.wins)" -ForegroundColor $wC -NoNewline; Write-Host " / " -NoNewline; Write-Host "$($cf.losses)" -ForegroundColor $lC
            Write-Host "   PnL         : " -NoNewline; Write-Host "$($cf.pnl_acumulado)%" -ForegroundColor $pC
        } else { Write-Host "   Wins / Loss :  sin trades aun" -ForegroundColor DarkGray }

        $bal = Get-CarpetaBalance -CarpetaId $carpeta
        if ($null -ne $bal) {
            $bC = if ($bal -ge 100) { "Green" } elseif ($bal -ge 90) { "Yellow" } else { "Red" }
            Write-Host "   Balance     : " -NoNewline; Write-Host "$bal USDT" -ForegroundColor $bC
        }

        if ($hb.issues -and $hb.issues.Count -gt 0) {
            Write-Host "   ALERTA      : " -NoNewline; Write-Host ($hb.issues -join " | ") -ForegroundColor Red
        }

    } catch {
        Write-Host "   Estado      : " -NoNewline; Write-Host "ERROR  ($($_.Exception.Message))" -ForegroundColor Red
    }
    Write-Host ""
}

# ── seccion Bot Manager  [carpeta 10] ────────────────────────────────────────

function Show-BotManager {
    param([object]$Metrics)
    $carpeta = "10"

    Write-Host "   --- Bot Manager  [carpeta $carpeta] ---" -ForegroundColor DarkCyan

    if (-not (Test-Path $HB_MANAGER)) {
        Write-Host "   Estado      : " -NoNewline; Write-Host "OFFLINE  (no levantado)" -ForegroundColor Red
        Write-Host ""; return
    }

    try {
        $hb  = Get-Content $HB_MANAGER -Encoding UTF8 -Raw -ErrorAction Stop | ConvertFrom-Json
        $age = Get-AgeSec -IsoTimestamp $hb.updated_at

        $st = $hb.status.ToUpper()
        $stColor = "Red"
        if     ($st -eq "OK")       { $stColor = "Green"  }
        elseif ($st -eq "STARTING") { $stColor = "Yellow" }

        Write-Host "   Estado      : " -NoNewline
        Write-Host $st -ForegroundColor $stColor -NoNewline
        $ageColor = Get-AgeColor -Sec $age -Warn 2100 -Error 4200
        Write-Host "  (hace $(Format-Age $age))" -ForegroundColor $ageColor

        $mode      = $hb.mode.ToUpper()
        $modeColor = if ($mode -eq "REAL") { "Red" } else { "Yellow" }
        Write-Host "   Modo        : " -NoNewline; Write-Host $mode -ForegroundColor $modeColor

        if ($hb.last_scan -and $hb.last_scan -ne "") {
            try {
                $scanDt  = [datetime]::Parse($hb.last_scan).ToLocalTime()
                $scanAgo = [math]::Round(([datetime]::Now - $scanDt).TotalMinutes, 0)
                $sC = if ($scanAgo -gt 70) { "Red" } elseif ($scanAgo -gt 35) { "Yellow" } else { "Green" }
                Write-Host "   Ultimo scan : " -NoNewline
                Write-Host "$($scanDt.ToString('HH:mm:ss'))  (hace ${scanAgo}min)" -ForegroundColor $sC
            } catch { Write-Host "   Ultimo scan :  $($hb.last_scan)" }
        } else {
            Write-Host "   Ultimo scan : " -NoNewline
            Write-Host "Pendiente (:00:05 o :30:05 UTC)" -ForegroundColor Yellow
        }

        $cf = $null
        if ($Metrics -and $Metrics.carpetas) { try { $cf = $Metrics.carpetas.$carpeta } catch {} }
        if ($cf -and $null -ne $cf.total_trades -and $cf.total_trades -gt 0) {
            $wC = if ($cf.wins   -gt 0) { "Green"   } else { "DarkGray" }
            $lC = if ($cf.losses -gt 0) { "Red"     } else { "DarkGray" }
            $pC = if ([double]$cf.pnl_acumulado -ge 0) { "Green" } else { "Red" }
            Write-Host "   Wins / Loss : " -NoNewline
            Write-Host "$($cf.wins)" -ForegroundColor $wC -NoNewline; Write-Host " / " -NoNewline; Write-Host "$($cf.losses)" -ForegroundColor $lC
            Write-Host "   PnL         : " -NoNewline; Write-Host "$($cf.pnl_acumulado)%" -ForegroundColor $pC
        } else { Write-Host "   Wins / Loss :  sin trades aun" -ForegroundColor DarkGray }

        $bal = Get-CarpetaBalance -CarpetaId $carpeta
        if ($null -ne $bal) {
            $bC = if ($bal -ge 100) { "Green" } elseif ($bal -ge 90) { "Yellow" } else { "Red" }
            Write-Host "   Balance     : " -NoNewline; Write-Host "$bal USDT" -ForegroundColor $bC
        }

        if ($hb.circuit_open -eq $true) {
            Write-Host "   ALERTA      : " -NoNewline; Write-Host "Circuit Breaker ABIERTO" -ForegroundColor Red
        }
        if ($hb.paused -eq $true) {
            Write-Host "   ALERTA      : " -NoNewline; Write-Host "Bot pausado (entradas bloqueadas)" -ForegroundColor Yellow
        }

    } catch {
        Write-Host "   Estado      : " -NoNewline; Write-Host "ERROR  ($($_.Exception.Message))" -ForegroundColor Red
    }
    Write-Host ""
}

# ── resultados globales (unica seccion de metricas) ───────────────────────────

function Show-ResultadosGlobales {
    param([object]$Metrics, [string[]]$CarpetasActivas)

    Write-Host "   --- Resultados Globales ---" -ForegroundColor DarkCyan

    $c = if ($Metrics) { $Metrics.consolidado } else { $null }

    if (-not $c -or $c.total_trades -eq 0) {
        Write-Host "   Sin trades registrados aun." -ForegroundColor DarkGray
        Write-Host ""; return
    }

    # Totales
    Write-Host "   Total trades : " -NoNewline; Write-Host $c.total_trades

    $wColor = if ($c.wins   -gt 0) { "Green"   } else { "DarkGray" }
    $lColor = if ($c.losses -gt 0) { "Red"     } else { "DarkGray" }
    Write-Host "   Wins         : " -NoNewline; Write-Host $c.wins   -ForegroundColor $wColor
    Write-Host "   Losses       : " -NoNewline; Write-Host $c.losses -ForegroundColor $lColor

    $wrColor = if ($c.winrate_pct -ge 55) { "Green" } elseif ($c.winrate_pct -ge 40) { "Yellow" } else { "Red" }
    Write-Host "   Win rate     : " -NoNewline; Write-Host "$($c.winrate_pct)%" -ForegroundColor $wrColor

    $pnlC = if ($c.pnl_acumulado -ge 0) { "Green" } else { "Red" }
    Write-Host "   PnL total    : " -NoNewline; Write-Host "$($c.pnl_acumulado)%" -ForegroundColor $pnlC

    # Balance total (suma de todas las carpetas activas)
    $balTotal = 0.0
    $balOk    = $false
    foreach ($id in $CarpetasActivas) {
        $b = Get-CarpetaBalance -CarpetaId $id
        if ($null -ne $b) { $balTotal += $b; $balOk = $true }
    }
    if ($balOk) {
        $balTotal = [math]::Round($balTotal, 2)
        $bC = if ($balTotal -ge (100 * $CarpetasActivas.Count)) { "Green" } elseif ($balTotal -ge (90 * $CarpetasActivas.Count)) { "Yellow" } else { "Red" }
        Write-Host "   Balance total: " -NoNewline; Write-Host "$balTotal USDT" -ForegroundColor $bC
    }

    # Ultimo trade de todas las carpetas
    $lastTrade = Get-LastTradeAllCarpetas -Ids $CarpetasActivas
    if ($lastTrade) {
        $ago      = 0
        try { $ago = [math]::Round((([datetime]::UtcNow) - ([datetime]$lastTrade.ts).ToUniversalTime()).TotalMinutes, 0) } catch {}
        $resColor = if ($lastTrade.resultado -eq "WIN") { "Green" } else { "Red" }
        $pnlNum   = try { [double]($lastTrade.pnl_pct -replace '[^0-9.+-]','') } catch { 0 }
        $pnlColor = if ($pnlNum -ge 0) { "Green" } else { "Red" }

        Write-Host ""
        Write-Host "   Ultimo trade : " -NoNewline
        Write-Host "$($lastTrade.resultado)" -ForegroundColor $resColor -NoNewline
        Write-Host "  Carpeta $($lastTrade.id_carpeta)  |  $($lastTrade.symbol)  |  hace ${ago}min"
        Write-Host "   PnL          : " -NoNewline; Write-Host "$($lastTrade.pnl_pct)" -ForegroundColor $pnlColor
        Write-Host "   Razon        :  $($lastTrade.close_reason)"
    }

    Write-Host ""
}

# ── esperar arranque ──────────────────────────────────────────────────────────

Write-Host ""
Write-Host " Esperando que el bot arranque..." -ForegroundColor DarkGray
$waited = 0
while ($waited -lt 20) {
    try { $null = Invoke-RestMethod "$url/" -TimeoutSec 2; break }
    catch { Start-Sleep -Seconds 1; $waited++ }
}

# ── loop principal ────────────────────────────────────────────────────────────

while ($true) {
    Clear-Host
    $ts = Get-Date -Format "yyyy-MM-dd  HH:mm:ss"

    Write-Host ""
    Write-Host " ==========================================" -ForegroundColor Cyan
    Write-Host "   BOT_EJECUTOR  --  Health Monitor" -ForegroundColor Cyan
    Write-Host " ==========================================" -ForegroundColor Cyan
    Write-Host "   $ts" -ForegroundColor DarkGray
    Write-Host ""

    $h = $null
    $m = $null

    try {
        $h = Invoke-RestMethod "$url/health"      -TimeoutSec 3
        $m = Invoke-RestMethod "$url/api/metrics" -TimeoutSec 3

        # ── Bot Ejecutor ──────────────────────────────────────────────────────
        Write-Host "   --- Bot Ejecutor ---" -ForegroundColor DarkCyan
        Write-Host "   Estado      : " -NoNewline; Write-Host "ONLINE" -ForegroundColor Green

        if ($h.dry_run_global -eq $true) {
            Write-Host "   Modo global : " -NoNewline; Write-Host "DRY_RUN  (sin ordenes reales)" -ForegroundColor Yellow
        } else {
            Write-Host "   Modo global : " -NoNewline; Write-Host "LIVE  *** ORDENES REALES ***" -ForegroundColor Red
        }

        Write-Host "   Carpetas    :  $($h.carpetas_activas -join ', ')"
        Write-Host "   Posiciones  :  $($h.posiciones_abiertas)"

        if ($h.carpetas_dry_run_local -and $h.carpetas_dry_run_local.Count -gt 0) {
            Write-Host "   Binance OFF :  " -NoNewline
            Write-Host ($h.carpetas_dry_run_local -join ", ") -ForegroundColor Yellow
        }
        Write-Host ""

    } catch {
        Write-Host "   --- Bot Ejecutor ---" -ForegroundColor DarkCyan
        Write-Host "   Estado      : " -NoNewline; Write-Host "OFFLINE" -ForegroundColor Red
        Write-Host "   $($_.Exception.Message)" -ForegroundColor DarkRed
        Write-Host ""
    }

    # ── Carpeta 1 + ngrok ─────────────────────────────────────────────────────
    Show-Carpeta1 -Metrics $m -Health $h

    # ── Bots externos ─────────────────────────────────────────────────────────
    Show-BotGrid    -Metrics $m
    Show-BotManager -Metrics $m

    # ── Resultados globales (unica seccion de metricas) ───────────────────────
    $idsActivos = if ($h -and $h.carpetas_activas) { $h.carpetas_activas } else { @("1","4","9","10") }
    Show-ResultadosGlobales -Metrics $m -CarpetasActivas $idsActivos

    Write-Host " ==========================================" -ForegroundColor Cyan
    Write-Host "   ngrok  : $NGROK_URL" -ForegroundColor DarkGray
    Write-Host "   local  : http://localhost:$Port/health" -ForegroundColor DarkGray
    Write-Host " ==========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   Actualizando en ${INTERVAL_SEC}s...  (Ctrl+C para cerrar)" -ForegroundColor DarkGray
    Write-Host ""

    Start-Sleep -Seconds $INTERVAL_SEC
}
