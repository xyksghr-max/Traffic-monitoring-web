#!/bin/bash
# 启动所有流处理服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "  Starting Streaming Services"
echo "========================================="

# 创建日志目录
mkdir -p "$PROJECT_DIR/logs"

# 启动任务生成器
echo "[1/3] Starting Task Generator..."
nohup python3 "$SCRIPT_DIR/start_task_generator.py" > "$PROJECT_DIR/logs/task_generator.log" 2>&1 &
TASK_GEN_PID=$!
echo "Task Generator started (PID: $TASK_GEN_PID)"
echo $TASK_GEN_PID > "$PROJECT_DIR/logs/task_generator.pid"

# 等待 2 秒
sleep 2

# 启动 LLM 调度器
echo "[2/3] Starting LLM Scheduler..."
nohup python3 "$SCRIPT_DIR/start_scheduler.py" > "$PROJECT_DIR/logs/scheduler.log" 2>&1 &
SCHEDULER_PID=$!
echo "LLM Scheduler started (PID: $SCHEDULER_PID)"
echo $SCHEDULER_PID > "$PROJECT_DIR/logs/scheduler.pid"

# 等待 2 秒
sleep 2

# 启动结果聚合器
echo "[3/3] Starting Result Aggregator..."
nohup python3 "$SCRIPT_DIR/start_result_aggregator.py" > "$PROJECT_DIR/logs/result_aggregator.log" 2>&1 &
AGGREGATOR_PID=$!
echo "Result Aggregator started (PID: $AGGREGATOR_PID)"
echo $AGGREGATOR_PID > "$PROJECT_DIR/logs/result_aggregator.pid"

echo ""
echo "========================================="
echo "  All services started successfully!"
echo "========================================="
echo ""
echo "Service PIDs:"
echo "  - Task Generator:    $TASK_GEN_PID"
echo "  - LLM Scheduler:     $SCHEDULER_PID"
echo "  - Result Aggregator: $AGGREGATOR_PID"
echo ""
echo "Log files:"
echo "  - Task Generator:    logs/task_generator.log"
echo "  - LLM Scheduler:     logs/scheduler.log"
echo "  - Result Aggregator: logs/result_aggregator.log"
echo ""
echo "To stop services, run: ./scripts/stop_streaming_services.sh"
echo "========================================="
