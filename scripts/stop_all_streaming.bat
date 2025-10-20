@echo off
REM ###############################################################################
REM 停止所有流式处理服务 (Windows)
REM ###############################################################################

setlocal enabledelayedexpansion

REM 获取项目根目录
set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
cd /d "%ROOT_DIR%"

echo ================================================================
echo              停止所有流式处理服务
echo ================================================================
echo.

REM ###############################################################################
REM Step 1: 停止 Python 进程
REM ###############################################################################
echo [Step 1/2] 停止 Python 流式服务...

REM 停止 Flask App
echo   停止 Flask App...
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq Flask App*" /NH 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
    echo   [成功] Flask App 已停止
)

REM 停止 Task Generator
echo   停止 Task Generator...
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq Task Generator*" /NH 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
    echo   [成功] Task Generator 已停止
)

REM 停止 LLM Scheduler
echo   停止 LLM Scheduler...
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq LLM Scheduler*" /NH 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
    echo   [成功] LLM Scheduler 已停止
)

REM 停止 Result Aggregator
echo   停止 Result Aggregator...
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq Result Aggregator*" /NH 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
    echo   [成功] Result Aggregator 已停止
)

REM 停止所有可能遗留的 Python 进程（运行启动脚本的）
echo   清理遗留的流式服务进程...
for /f "tokens=2" %%a in ('wmic process where "commandline like '%%start_task_generator%%' or commandline like '%%start_scheduler%%' or commandline like '%%start_result_aggregator%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo [成功] 所有 Python 服务已停止
echo.

REM ###############################################################################
REM Step 2: 停止 Docker 基础设施
REM ###############################################################################
echo [Step 2/2] 停止基础设施 (Docker)...

if exist "deployment\docker-compose.infra.yml" (
    cd deployment
    docker-compose -f docker-compose.infra.yml down
    cd ..
    echo [成功] 基础设施已停止
) else (
    echo [警告] deployment\docker-compose.infra.yml 不存在
)
echo.

echo ================================================================
echo                   所有服务已停止
echo ================================================================
echo.

echo 提示：
echo   - 使用 'docker ps' 确认容器已停止
echo   - 使用任务管理器确认进程已停止
echo.
pause
