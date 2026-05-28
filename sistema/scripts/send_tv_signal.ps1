# send_tv_signal.ps1 - Plan B: envia una senal TV manualmente al endpoint /webhook/tv
# Uso: .\scripts\send_tv_signal.ps1

$url    = "http://localhost:8001/webhook/tv"
$secret = $env:TV_WEBHOOK_SECRET

if (-not $secret) {
    Write-Host "ERROR: TV_WEBHOOK_SECRET no esta definido en el entorno." -ForegroundColor Red
    exit 1
}

$body = @{
    timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    status    = "pending"
    processed = $false
    source    = "tradingview"
    signal    = @{
        strategy_id = "strategy_tv_qlearning"
        symbol      = "SPY"
        action      = "buy"
        confidence  = 0.75
        size        = 0.1
        params      = @{
            price      = 512.30
            sl         = 510.20
            tp         = 516.50
            atr        = 1.45
            regime     = "trend_up"
            volatility = "mid"
            momentum   = "bullish"
        }
    }
} | ConvertTo-Json -Depth 5

Write-Host "Enviando senal a $url ..." -ForegroundColor Cyan

$response = Invoke-RestMethod `
    -Uri     $url `
    -Method  POST `
    -Headers @{"Content-Type" = "application/json"; "X-Webhook-Secret" = $secret} `
    -Body    $body

$response | ConvertTo-Json -Depth 5
