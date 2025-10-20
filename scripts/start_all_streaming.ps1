###############################################################################
# 一键启动所有流式处理服务 (PowerShell)
# 
# 功能：
#   - 启动 Kafka 和相关基础设施（Zookeeper, Redis, Prometheus, Grafana）
#   - 初始化 Kafka Topics
#   - 启动 3 个流式处理服务（Task Generator, Scheduler, Result Aggregator）
#   - 启动 Flask 应用
#
# 使用方法：
#   .\scripts\start_all_streaming.ps1
#
# 停止服务：
#   .\scripts\stop_all_streaming.ps1
###############################################################################

# 设置错误处理
$ErrorActionPreference = "Stop"

# 颜色定义函数
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

# 获取项目根目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
Set-Location $RootDir

# 日志目录
$LogDir = Join-Path $RootDir "logs\streaming"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# PID 目录
$PidDir = Join-Path $RootDir "logs\pids"
if (-not (Test-Path $PidDir)) {
    New-Item -ItemType Directory -Path $PidDir -Force | Out-Null
}

Write-Host ""
Write-ColorOutput "================================================================" "Cyan"
Write-ColorOutput "           一键启动流式处理服务 (Kafka Streaming)" "Cyan"
Write-ColorOutput "================================================================" "Cyan"
Write-Host ""

###############################################################################
# Step 1: 检查 Docker 环境
###############################################################################
Write-ColorOutput "[Step 1/6] 检查 Docker 环境..." "Yellow"

try {
    $dockerVersion = docker --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker 未安装"
    }
} catch {
    Write-ColorOutput "[错误] Docker 未安装" "Red"
    Write-Host "请先安装 Docker Desktop: https://docs.docker.com/desktop/windows/install/"
    Read-Host "按任意键退出"
    exit 1
}

try {
    $dockerComposeVersion = docker-compose --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose 未安装"
    }
} catch {
    Write-ColorOutput "[错误] Docker Compose 未安装" "Red"
    Write-Host "Docker Desktop 应该自带 docker-compose"
    Read-Host "按任意键退出"
    exit 1
}

Write-ColorOutput "[成功] Docker 环境正常" "Green"
Write-Host ""

###############################################################################
# Step 2: 启动基础设施服务
###############################################################################
Write-ColorOutput "[Step 2/6] 启动基础设施 (Kafka, Redis, Prometheus, Grafana)..." "Yellow"

$dockerComposeFile = Join-Path $RootDir "deployment\docker-compose.infra.yml"
if (Test-Path $dockerComposeFile) {
    Push-Location (Join-Path $RootDir "deployment")
    try {
        docker-compose -f docker-compose.infra.yml up -d
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose 启动失败"
        }
        Write-ColorOutput "[成功] 基础设施启动成功" "Green"
    } catch {
        Write-ColorOutput "[错误] 基础设施启动失败: $_" "Red"
        Pop-Location
        Read-Host "按任意键退出"
        exit 1
    }
    Pop-Location
} else {
    Write-ColorOutput "[错误] deployment\docker-compose.infra.yml 不存在" "Red"
    Read-Host "按任意键退出"
    exit 1
}

Write-Host "等待服务就绪 (10秒)..."
Start-Sleep -Seconds 10
Write-Host ""

###############################################################################
# Step 3: 初始化 Kafka Topics
###############################################################################
Write-ColorOutput "[Step 3/6] 初始化 Kafka Topics..." "Yellow"

$initKafkaScript = Join-Path $RootDir "scripts\init_kafka_topics.py"
if (Test-Path $initKafkaScript) {
    try {
        python $initKafkaScript
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput "[警告] Kafka Topics 初始化失败，但继续执行" "Yellow"
        } else {
            Write-ColorOutput "[成功] Kafka Topics 初始化成功" "Green"
        }
    } catch {
        Write-ColorOutput "[警告] Kafka Topics 初始化出错: $_" "Yellow"
    }
} else {
    Write-ColorOutput "[警告] scripts\init_kafka_topics.py 不存在，跳过 Topic 初始化" "Yellow"
}
Write-Host ""

###############################################################################
# Step 4: 启动流式处理服务
###############################################################################
Write-ColorOutput "[Step 4/6] 启动流式处理服务..." "Yellow"

# 4.1 Task Generator
Write-Host "  启动 Task Generator..."
$taskGenScript = Join-Path $RootDir "scripts\start_task_generator.py"
$taskGenLog = Join-Path $LogDir "task_generator.log"

$taskGenProcess = Start-Process -FilePath "python" -ArgumentList $taskGenScript `
    -WindowStyle Minimized -PassThru -RedirectStandardOutput $taskGenLog `
    -RedirectStandardError (Join-Path $LogDir "task_generator_error.log")

Start-Sleep -Seconds 2
Write-ColorOutput "  [成功] Task Generator 已启动 (PID: $($taskGenProcess.Id))" "Green"

# 保存 PID
$taskGenProcess.Id | Out-File (Join-Path $PidDir "task_generator.pid")

# 4.2 LLM Scheduler
Write-Host "  启动 LLM Scheduler..."
$schedulerScript = Join-Path $RootDir "scripts\start_scheduler.py"
$schedulerLog = Join-Path $LogDir "scheduler.log"

$schedulerProcess = Start-Process -FilePath "python" -ArgumentList $schedulerScript `
    -WindowStyle Minimized -PassThru -RedirectStandardOutput $schedulerLog `
    -RedirectStandardError (Join-Path $LogDir "scheduler_error.log")

Start-Sleep -Seconds 2
Write-ColorOutput "  [成功] LLM Scheduler 已启动 (PID: $($schedulerProcess.Id))" "Green"

# 保存 PID
$schedulerProcess.Id | Out-File (Join-Path $PidDir "scheduler.pid")

# 4.3 Result Aggregator
Write-Host "  启动 Result Aggregator..."
$aggregatorScript = Join-Path $RootDir "scripts\start_result_aggregator.py"
$aggregatorLog = Join-Path $LogDir "result_aggregator.log"

$aggregatorProcess = Start-Process -FilePath "python" -ArgumentList $aggregatorScript `
    -WindowStyle Minimized -PassThru -RedirectStandardOutput $aggregatorLog `
    -RedirectStandardError (Join-Path $LogDir "result_aggregator_error.log")

Start-Sleep -Seconds 2
Write-ColorOutput "  [成功] Result Aggregator 已启动 (PID: $($aggregatorProcess.Id))" "Green"

# 保存 PID
$aggregatorProcess.Id | Out-File (Join-Path $PidDir "result_aggregator.pid")

Write-ColorOutput "[成功] 所有流式服务启动成功" "Green"
Write-Host ""

###############################################################################
# Step 5: 启动 Flask 应用 (Kafka 模式)
###############################################################################
Write-ColorOutput "[Step 5/6] 启动 Flask 应用 (Kafka 流式模式)..." "Yellow"

$env:ALGO_ENABLE_KAFKA_STREAMING = "true"

$flaskScript = Join-Path $RootDir "app.py"
$flaskLog = Join-Path $LogDir "flask_app.log"

$flaskProcess = Start-Process -FilePath "python" -ArgumentList $flaskScript `
    -WindowStyle Minimized -PassThru -RedirectStandardOutput $flaskLog `
    -RedirectStandardError (Join-Path $LogDir "flask_app_error.log")

# 保存 PID
$flaskProcess.Id | Out-File (Join-Path $PidDir "flask_app.pid")

Write-ColorOutput "[成功] Flask 应用启动成功 (PID: $($flaskProcess.Id))" "Green"
Write-Host ""

###############################################################################
# Step 6: 验证服务状态
###############################################################################
Write-ColorOutput "[Step 6/6] 验证服务状态..." "Yellow"

Write-Host "等待服务完全启动 (5秒)..."
Start-Sleep -Seconds 5
Write-Host ""

Write-ColorOutput "================================================================" "Cyan"
Write-ColorOutput "                   所有服务启动完成！" "Cyan"
Write-ColorOutput "================================================================" "Cyan"
Write-Host ""

Write-Host "服务访问地址："
Write-ColorOutput "  • Flask 应用:       http://localhost:5000" "White"
Write-ColorOutput "  • Prometheus 指标:  http://localhost:5000/metrics" "White"
Write-ColorOutput "  • Prometheus UI:    http://localhost:9100" "White"
Write-ColorOutput "  • Grafana:          http://localhost:3100 (admin/admin)" "White"
Write-Host ""

Write-Host "日志文件："
Write-ColorOutput "  • Task Generator:    $LogDir\task_generator.log" "White"
Write-ColorOutput "  • LLM Scheduler:     $LogDir\scheduler.log" "White"
Write-ColorOutput "  • Result Aggregator: $LogDir\result_aggregator.log" "White"
Write-ColorOutput "  • Flask App:         $LogDir\flask_app.log" "White"
Write-Host ""

Write-Host "PID 文件："
Write-ColorOutput "  • 所有进程 PID 保存在: $PidDir" "White"
Write-Host ""

Write-Host "停止所有服务："
Write-ColorOutput "  .\scripts\stop_all_streaming.ps1" "Yellow"
Write-Host ""

Write-Host "提示："
Write-Host "  - 使用任务管理器查看进程状态"
Write-Host "  - 使用 'docker ps' 查看基础设施容器状态"
Write-Host "  - 使用 'Get-NetTCPConnection -LocalPort 5000' 查看端口占用"
Write-Host "  - 使用 'Get-Process python' 查看 Python 进程"
Write-Host ""

Write-ColorOutput "[成功] 启动完成！系统已准备就绪。" "Green"
Write-Host ""

Read-Host "按 Enter 键退出"
