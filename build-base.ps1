#!/usr/bin/env pwsh
# Build the base Docker image with all heavy dependencies
# Run this once at the start of your hackathon, or when dependencies change

Write-Host "Building base image with all dependencies..." -ForegroundColor Cyan
Write-Host "This will take ~45 minutes (one-time cost)" -ForegroundColor Yellow
Write-Host ""

$startTime = Get-Date

docker build -f Dockerfile.base -t mammothbox-base:latest .

if ($LASTEXITCODE -eq 0) {
    $duration = (Get-Date) - $startTime
    Write-Host ""
    Write-Host "✓ Base image built successfully in $($duration.ToString('mm\:ss'))" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Build app: docker-compose build" -ForegroundColor White
    Write-Host "  2. Start system: docker-compose up -d" -ForegroundColor White
    Write-Host ""
    Write-Host "Future code changes will build in ~5 seconds!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "✗ Build failed" -ForegroundColor Red
    exit 1
}
