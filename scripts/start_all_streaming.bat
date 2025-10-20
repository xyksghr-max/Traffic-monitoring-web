@echo off
REM ###############################################################################
REM 一键启动所有流式处理服务 (Windows)
REM 
REM 功能：
REM   - 启动 Kafka 和相关基础设施（Zookeeper, Redis, Prometheus, Grafana）
REM   - 初始化 Kafka Topics
REM   - 启动 3 个流式处理服务（Task Generator, Scheduler, Result Aggregator）
REM   - 启动 Flask 应用
REM
REM 使用方法：
REM   scripts\start_all_streaming.bat
REM
REM 停止服务：
REM   scripts\stop_all_streaming.bat
REM ###############################################################################

setlocal enabledelayedexpansion

REM 获取项目根目录
set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
cd /d "%ROOT_DIR%"

REM 日志目录
set "LOG_DIR=%ROOT_DIR%\logs\streaming"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM PID 目录
set "PID_DIR=%ROOT_DIR%\logs\pids"
if not exist "%PID_DIR%" mkdir "%PID_DIR%"

echo ================================================================
echo           一键启动流式处理服务 (Kafka Streaming)
echo ================================================================
echo.

REM ###############################################################################
REM Step 1: 检查 Docker 环境
REM ###############################################################################
echo [Step 1/6] 检查 Docker 环境...

where docker >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] Docker 未安装
    echo 请先安装 Docker Desktop: https://docs.docker.com/desktop/windows/install/
    pause
    exit /b 1
)

where docker-compose >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] Docker Compose 未安装
    echo Docker Desktop 应该自带 docker-compose
    pause
    exit /b 1
)

echo [成功] Docker 环境正常
echo.

REM ###############################################################################
REM Step 2: 启动基础设施服务
REM ###############################################################################
echo [Step 2/6] 启动基础设施 (Kafka, Redis, Prometheus, Grafana)...

if exist "deployment\docker-compose.infra.yml" (
    cd deployment
    docker-compose -f docker-compose.infra.yml up -d
    cd ..
    echo [成功] 基础设施启动成功
) else (
    echo [错误] deployment\docker-compose.infra.yml 不存在
    pause
    exit /b 1
)

echo 等待服务就绪 (10秒)...
timeout /t 10 /nobreak >nul
echo.

REM ###############################################################################
REM Step 3: 初始化 Kafka Topics
REM ###############################################################################
echo [Step 3/6] 初始化 Kafka Topics...

if exist "scripts\init_kafka_topics.py" (
    python scripts\init_kafka_topics.py
    echo [成功] Kafka Topics 初始化成功
) else (
    echo [警告] scripts\init_kafka_topics.py 不存在，跳过 Topic 初始化
)
echo.

REM ###############################################################################
REM Step 4: 启动流式处理服务
REM ###############################################################################
echo [Step 4/6] 启动流式处理服务...

REM 4.1 Task Generator
echo   启动 Task Generator...
start "Task Generator" /min python scripts\start_task_generator.py
timeout /t 2 /nobreak >nul
echo   [成功] Task Generator 已启动

REM 4.2 LLM Scheduler
echo   启动 LLM Scheduler...
start "LLM Scheduler" /min python scripts\start_scheduler.py
timeout /t 2 /nobreak >nul
echo   [成功] LLM Scheduler 已启动

REM 4.3 Result Aggregator
echo   启动 Result Aggregator...
start "Result Aggregator" /min python scripts\start_result_aggregator.py
timeout /t 2 /nobreak >nul
echo   [成功] Result Aggregator 已启动

echo [成功] 所有流式服务启动成功
echo.

REM ###############################################################################
REM Step 5: 启动 Flask 应用 (Kafka 模式)
REM ###############################################################################
echo [Step 5/6] 启动 Flask 应用 (Kafka 流式模式)...

set ALGO_ENABLE_KAFKA_STREAMING=true

start "Flask App" /min python app.py
echo [成功] Flask 应用启动成功
echo.

REM ###############################################################################
REM Step 6: 验证服务状态
REM ###############################################################################
echo [Step 6/6] 验证服务状态...

echo 等待服务完全启动 (5秒)...
timeout /t 5 /nobreak >nul
echo.

echo ================================================================
echo                   所有服务启动完成！
echo ================================================================
echo.

echo 服务访问地址：
echo   • Flask 应用:       http://localhost:5000
echo   • Prometheus 指标:  http://localhost:5000/metrics
echo   • Prometheus UI:    http://localhost:9100
echo   • Grafana:          http://localhost:3100 (admin/admin)
echo.

echo 日志文件：
echo   • Task Generator:   %LOG_DIR%\task_generator.log
echo   • LLM Scheduler:    %LOG_DIR%\scheduler.log
echo   • Result Aggregator: %LOG_DIR%\result_aggregator.log
echo   • Flask App:        %LOG_DIR%\flask_app.log
echo.

echo 停止所有服务：
echo   scripts\stop_all_streaming.bat
echo.

echo 提示：
echo   - 使用任务管理器查看进程状态
echo   - 使用 'docker ps' 查看基础设施容器状态
echo   - 使用 'netstat -ano ^| findstr :5000' 查看端口占用
echo.

echo [成功] 启动完成！系统已准备就绪。
echo.
pause
