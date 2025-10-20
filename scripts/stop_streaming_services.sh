#!/bin/bash
# 停止所有流处理服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "  Stopping Streaming Services"
echo "========================================="

# 停止任务生成器
if [ -f "$PROJECT_DIR/logs/task_generator.pid" ]; then
    TASK_GEN_PID=$(cat "$PROJECT_DIR/logs/task_generator.pid")
    echo "[1/3] Stopping Task Generator (PID: $TASK_GEN_PID)..."
    kill $TASK_GEN_PID 2>/dev/null || echo "  Process already stopped"
    rm -f "$PROJECT_DIR/logs/task_generator.pid"
else
    echo "[1/3] Task Generator PID file not found"
fi

# 停止 LLM 调度器
if [ -f "$PROJECT_DIR/logs/scheduler.pid" ]; then
    SCHEDULER_PID=$(cat "$PROJECT_DIR/logs/scheduler.pid")
    echo "[2/3] Stopping LLM Scheduler (PID: $SCHEDULER_PID)..."
    kill $SCHEDULER_PID 2>/dev/null || echo "  Process already stopped"
    rm -f "$PROJECT_DIR/logs/scheduler.pid"
else
    echo "[2/3] LLM Scheduler PID file not found"
fi

# 停止结果聚合器
if [ -f "$PROJECT_DIR/logs/result_aggregator.pid" ]; then
    AGGREGATOR_PID=$(cat "$PROJECT_DIR/logs/result_aggregator.pid")
    echo "[3/3] Stopping Result Aggregator (PID: $AGGREGATOR_PID)..."
    kill $AGGREGATOR_PID 2>/dev/null || echo "  Process already stopped"
    rm -f "$PROJECT_DIR/logs/result_aggregator.pid"
else
    echo "[3/3] Result Aggregator PID file not found"
fi

echo ""
echo "========================================="
echo "  All services stopped"
echo "========================================="
