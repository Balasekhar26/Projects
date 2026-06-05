# Kronos Finance Brain

Universal AI now has a Finance Brain for OHLCV/K-line market data.

## What Was Installed

- Kronos source: `<Projects root>\external-projects\Kronos` or `<Projects root>\bin\external-projects\Kronos`
- License: MIT
- Universal AI adapter: `backend\tools\finance_brain.py`
- Finance agent: `backend\agents\finance.py`
- API endpoints:
  - `GET /finance/kronos/status`
  - `POST /finance/forecast`
  - `POST /finance/forecast-csv`

## How To Use It

Kronos needs structured candles, not chat text:

```json
{
  "candles": [
    {"timestamp": "2026-05-31T10:00:00", "open": 67200, "high": 67400, "low": 67120, "close": 67350, "volume": 1200},
    {"timestamp": "2026-05-31T10:05:00", "open": 67350, "high": 67510, "low": 67280, "close": 67490, "volume": 980},
    {"timestamp": "2026-05-31T10:10:00", "open": 67490, "high": 67600, "low": 67410, "close": 67540, "volume": 1100}
  ],
  "horizon": 5,
  "use_kronos": false
}
```

PowerShell:

```powershell
$body = @{
  candles = @(
    @{ timestamp = "2026-05-31T10:00:00"; open = 67200; high = 67400; low = 67120; close = 67350; volume = 1200 },
    @{ timestamp = "2026-05-31T10:05:00"; open = 67350; high = 67510; low = 67280; close = 67490; volume = 980 },
    @{ timestamp = "2026-05-31T10:10:00"; open = 67490; high = 67600; low = 67410; close = 67540; volume = 1100 }
  )
  horizon = 5
  use_kronos = $false
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/finance/forecast -Body $body -ContentType "application/json"
```

CSV:

```powershell
$body = @{
  path = "C:\path\to\ohlcv.csv"
  horizon = 12
  use_kronos = $false
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/finance/forecast-csv -Body $body -ContentType "application/json"
```

## Local Fallback vs Real Kronos

`use_kronos=false` uses Sekhar AI OS's own small OHLCV baseline forecaster. It is fast, local, and good for testing the full pipeline.

`use_kronos=true` calls the real Kronos adapter. The first real run can download model weights from Hugging Face:

- Tokenizer: `NeoQuasar/Kronos-Tokenizer-base`
- Model: `NeoQuasar/Kronos-small`

Use real Kronos with longer candle history. At least 128 candles is better than a tiny sample.

## Build-Own Boundary

Universal AI did not blindly copy Kronos into its core brain. Kronos stays as an external MIT-licensed reference and optional model adapter. The owned Universal AI layer handles:

- OHLCV validation
- CSV loading
- local baseline forecast
- risk warning
- FastAPI endpoints
- chat-agent routing
- swappable model boundary

This keeps the system useful now while leaving room to train a future custom financial model.

## Safety

Outputs are market analysis only. They are not guaranteed trading signals or financial advice.
