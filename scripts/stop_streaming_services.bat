@echo off
REM ========================================
REM Windows 批处理脚本：停止流处理服务
REM ========================================

setlocal enabledelayedexpansion

echo ========================================
echo 停止流处理服务 (Windows)
echo ========================================

REM 停止 Task Generator
echo [1/3] 停止任务生成器...
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "start_task_generator"') do (
    taskkill /PID %%a /F >nul 2>&1
    if !errorlevel! equ 0 (
        echo   ✓ 任务生成器已停止 (PID: %%a)
    )
)

REM 停止 LLM Scheduler
echo [2/3] 停止 LLM 调度器...
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "start_scheduler"') do (
    taskkill /PID %%a /F >nul 2>&1
    if !errorlevel! equ 0 (
        echo   ✓ LLM 调度器已停止 (PID: %%a)
    )
)

REM 停止 Result Aggregator
echo [3/3] 停止结果聚合器...
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "start_result_aggregator"') do (
    taskkill /PID %%a /F >nul 2>&1
    if !errorlevel! equ 0 (
        echo   ✓ 结果聚合器已停止 (PID: %%a)
    )
)

echo.
echo ========================================
echo ✓ 所有服务已停止
echo ========================================

endlocal
