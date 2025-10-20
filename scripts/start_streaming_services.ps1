# ========================================
# PowerShell 脚本：启动流处理服务
# ========================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "启动流处理服务 (PowerShell)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 检查 Python 是否可用
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[错误] Python 未安装或不在 PATH 中" -ForegroundColor Red
    exit 1
}

# 切换到项目根目录
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptPath "..")

# 创建日志目录
$logDir = "logs\streaming"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

Write-Host ""
Write-Host "[1/3] 启动任务生成器..." -ForegroundColor Yellow

# 启动任务生成器
$taskGenLog = Join-Path $logDir "task_generator.log"
$taskGenProcess = Start-Process -FilePath "python" `
    -ArgumentList "scripts\start_task_generator.py" `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput $taskGenLog `
    -RedirectStandardError "$logDir\task_generator.err.log"

if ($taskGenProcess) {
    Write-Host "  ✓ 任务生成器已启动 (PID: $($taskGenProcess.Id))" -ForegroundColor Green
    # 保存 PID
    $taskGenProcess.Id | Out-File -FilePath "$logDir\task_generator.pid"
} else {
    Write-Host "  ✗ 任务生成器启动失败" -ForegroundColor Red
    exit 1
}

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "[2/3] 启动 LLM 调度器..." -ForegroundColor Yellow

# 启动 LLM 调度器
$schedulerLog = Join-Path $logDir "scheduler.log"
$schedulerProcess = Start-Process -FilePath "python" `
    -ArgumentList "scripts\start_scheduler.py" `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput $schedulerLog `
    -RedirectStandardError "$logDir\scheduler.err.log"

if ($schedulerProcess) {
    Write-Host "  ✓ LLM 调度器已启动 (PID: $($schedulerProcess.Id))" -ForegroundColor Green
    # 保存 PID
    $schedulerProcess.Id | Out-File -FilePath "$logDir\scheduler.pid"
} else {
    Write-Host "  ✗ LLM 调度器启动失败" -ForegroundColor Red
    exit 1
}

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "[3/3] 启动结果聚合器..." -ForegroundColor Yellow

# 启动结果聚合器
$aggregatorLog = Join-Path $logDir "aggregator.log"
$aggregatorProcess = Start-Process -FilePath "python" `
    -ArgumentList "scripts\start_result_aggregator.py" `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput $aggregatorLog `
    -RedirectStandardError "$logDir\aggregator.err.log"

if ($aggregatorProcess) {
    Write-Host "  ✓ 结果聚合器已启动 (PID: $($aggregatorProcess.Id))" -ForegroundColor Green
    # 保存 PID
    $aggregatorProcess.Id | Out-File -FilePath "$logDir\aggregator.pid"
} else {
    Write-Host "  ✗ 结果聚合器启动失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✓ 所有服务已启动完成" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "日志目录: $logDir" -ForegroundColor White
Write-Host ""
Write-Host "使用以下命令查看日志:" -ForegroundColor White
Write-Host "  - 任务生成器: Get-Content $taskGenLog -Tail 50 -Wait" -ForegroundColor Gray
Write-Host "  - LLM 调度器: Get-Content $schedulerLog -Tail 50 -Wait" -ForegroundColor Gray
Write-Host "  - 结果聚合器: Get-Content $aggregatorLog -Tail 50 -Wait" -ForegroundColor Gray
Write-Host ""
Write-Host "停止所有服务: .\stop_streaming_services.ps1" -ForegroundColor Yellow
Write-Host ""
