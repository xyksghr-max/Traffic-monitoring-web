@echo off
REM ========================================
REM Windows 批处理脚本：启动流处理服务
REM ========================================

setlocal enabledelayedexpansion

echo ========================================
echo 启动流处理服务 (Windows)
echo ========================================

REM 检查 Python 是否可用
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Python 未安装或不在 PATH 中
    exit /b 1
)

REM 设置工作目录为项目根目录
cd /d %~dp0..

REM 设置日志目录
set LOG_DIR=logs\streaming
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo.
echo [1/3] 启动任务生成器...
start "Task Generator" /min python scripts\start_task_generator.py > "%LOG_DIR%\task_generator.log" 2>&1
if %errorlevel% neq 0 (
    echo [错误] 任务生成器启动失败
    exit /b 1
)
echo   ✓ 任务生成器已启动

timeout /t 2 /nobreak >nul

echo.
echo [2/3] 启动 LLM 调度器...
start "LLM Scheduler" /min python scripts\start_scheduler.py > "%LOG_DIR%\scheduler.log" 2>&1
if %errorlevel% neq 0 (
    echo [错误] LLM 调度器启动失败
    exit /b 1
)
echo   ✓ LLM 调度器已启动

timeout /t 2 /nobreak >nul

echo.
echo [3/3] 启动结果聚合器...
start "Result Aggregator" /min python scripts\start_result_aggregator.py > "%LOG_DIR%\aggregator.log" 2>&1
if %errorlevel% neq 0 (
    echo [错误] 结果聚合器启动失败
    exit /b 1
)
echo   ✓ 结果聚合器已启动

echo.
echo ========================================
echo ✓ 所有服务已启动完成
echo ========================================
echo.
echo 日志目录: %LOG_DIR%
echo.
echo 使用以下命令查看日志:
echo   - 任务生成器: type %LOG_DIR%\task_generator.log
echo   - LLM 调度器: type %LOG_DIR%\scheduler.log
echo   - 结果聚合器: type %LOG_DIR%\aggregator.log
echo.
echo 停止所有服务: stop_streaming_services.bat
echo.

endlocal
