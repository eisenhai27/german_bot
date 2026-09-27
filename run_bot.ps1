# Starts the bot on this computer in polling mode.
# Asks for the bot token each time (it is never saved to disk).
# Run with:  powershell -ExecutionPolicy Bypass -File .\run_bot.ps1

Set-Location $PSScriptRoot

if (-not $env:BOT_TOKEN) {
    $secure = Read-Host "Paste your bot token from @BotFather (right-click to paste), then press Enter" -AsSecureString
    $env:BOT_TOKEN = [System.Net.NetworkCredential]::new("", $secure).Password
}
if (-not $env:MINI_APP_URL) {
    $env:MINI_APP_URL = "https://eisenhai27.github.io/german_bot/miniapp/"
}

Write-Host "Starting bot... keep this window open. Press Ctrl+C to stop."
python polling_app.py
