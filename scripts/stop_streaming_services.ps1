# ========================================
# PowerShell 脚本：停止流处理服务
# ========================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "停止流处理服务 (PowerShell)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 切换到项目根目录
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptPath "..")

$logDir = "logs\streaming"
$stopped = 0

# 停止任务生成器
Write-Host "[1/3] 停止任务生成器..." -ForegroundColor Yellow
$pidFile = Join-Path $logDir "task_generator.pid"
if (Test-Path $pidFile) {
    $pid = Get-Content $pidFile
    try {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ 任务生成器已停止 (PID: $pid)" -ForegroundColor Green
        Remove-Item $pidFile -Force
        $stopped++
    } catch {
        Write-Host "  ⚠ 无法停止任务生成器 (PID: $pid)" -ForegroundColor Yellow
    }
} else {
    # 尝试通过进程名查找并停止
    $processes = Get-Process | Where-Object { $_.CommandLine -like "*start_task_generator.py*" } -ErrorAction SilentlyContinue
    if ($processes) {
        $processes | Stop-Process -Force
        Write-Host "  ✓ 任务生成器已停止" -ForegroundColor Green
        $stopped++
    } else {
        Write-Host "  - 任务生成器未运行" -ForegroundColor Gray
    }
}

# 停止 LLM 调度器
Write-Host "[2/3] 停止 LLM 调度器..." -ForegroundColor Yellow
$pidFile = Join-Path $logDir "scheduler.pid"
if (Test-Path $pidFile) {
    $pid = Get-Content $pidFile
    try {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ LLM 调度器已停止 (PID: $pid)" -ForegroundColor Green
        Remove-Item $pidFile -Force
        $stopped++
    } catch {
        Write-Host "  ⚠ 无法停止 LLM 调度器 (PID: $pid)" -ForegroundColor Yellow
    }
} else {
    # 尝试通过进程名查找并停止
    $processes = Get-Process | Where-Object { $_.CommandLine -like "*start_scheduler.py*" } -ErrorAction SilentlyContinue
    if ($processes) {
        $processes | Stop-Process -Force
        Write-Host "  ✓ LLM 调度器已停止" -ForegroundColor Green
        $stopped++
    } else {
        Write-Host "  - LLM 调度器未运行" -ForegroundColor Gray
    }
}

# 停止结果聚合器
Write-Host "[3/3] 停止结果聚合器..." -ForegroundColor Yellow
$pidFile = Join-Path $logDir "aggregator.pid"
if (Test-Path $pidFile) {
    $pid = Get-Content $pidFile
    try {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ 结果聚合器已停止 (PID: $pid)" -ForegroundColor Green
        Remove-Item $pidFile -Force
        $stopped++
    } catch {
        Write-Host "  ⚠ 无法停止结果聚合器 (PID: $pid)" -ForegroundColor Yellow
    }
} else {
    # 尝试通过进程名查找并停止
    $processes = Get-Process | Where-Object { $_.CommandLine -like "*start_result_aggregator.py*" } -ErrorAction SilentlyContinue
    if ($processes) {
        $processes | Stop-Process -Force
        Write-Host "  ✓ 结果聚合器已停止" -ForegroundColor Green
        $stopped++
    } else {
        Write-Host "  - 结果聚合器未运行" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✓ 已停止 $stopped 个服务" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
