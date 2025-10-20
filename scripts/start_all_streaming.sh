#!/bin/bash
###############################################################################
# 一键启动所有流式处理服务
# 
# 功能：
#   - 启动 Kafka 和相关基础设施（Zookeeper, Redis, Prometheus, Grafana）
#   - 初始化 Kafka Topics
#   - 启动 3 个流式处理服务（Task Generator, Scheduler, Result Aggregator）
#   - 启动 Flask 应用
#
# 使用方法：
#   ./scripts/start_all_streaming.sh
#
# 停止服务：
#   ./scripts/stop_all_streaming.sh
###############################################################################

set -e  # Exit on error

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

# 日志目录
LOG_DIR="$ROOT_DIR/logs/streaming"
mkdir -p "$LOG_DIR"

# PID 目录
PID_DIR="$ROOT_DIR/logs/pids"
mkdir -p "$PID_DIR"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          一键启动流式处理服务 (Kafka Streaming)              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

###############################################################################
# Step 1: 检查并启动基础设施 (Docker)
###############################################################################
echo -e "${YELLOW}[Step 1/6]${NC} 检查 Docker 环境..."

if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker 未安装${NC}"
    echo "请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}错误: Docker Compose 未安装${NC}"
    echo "请先安装 Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

echo -e "${GREEN}✓ Docker 环境正常${NC}"
echo ""

###############################################################################
# Step 2: 启动基础设施服务
###############################################################################
echo -e "${YELLOW}[Step 2/6]${NC} 启动基础设施 (Kafka, Redis, Prometheus, Grafana)..."

if [ -f "deployment/docker-compose.infra.yml" ]; then
    cd deployment
    docker-compose -f docker-compose.infra.yml up -d
    cd ..
    echo -e "${GREEN}✓ 基础设施启动成功${NC}"
else
    echo -e "${RED}错误: deployment/docker-compose.infra.yml 不存在${NC}"
    exit 1
fi

echo "等待服务就绪 (10秒)..."
sleep 10
echo ""

###############################################################################
# Step 3: 初始化 Kafka Topics
###############################################################################
echo -e "${YELLOW}[Step 3/6]${NC} 初始化 Kafka Topics..."

if [ -f "scripts/init_kafka_topics.py" ]; then
    python scripts/init_kafka_topics.py
    echo -e "${GREEN}✓ Kafka Topics 初始化成功${NC}"
else
    echo -e "${YELLOW}警告: scripts/init_kafka_topics.py 不存在，跳过 Topic 初始化${NC}"
fi
echo ""

###############################################################################
# Step 4: 启动流式处理服务
###############################################################################
echo -e "${YELLOW}[Step 4/6]${NC} 启动流式处理服务..."

# 4.1 Task Generator
echo "  → 启动 Task Generator..."
nohup python scripts/start_task_generator.py > "$LOG_DIR/task_generator.log" 2>&1 &
TASK_GEN_PID=$!
echo $TASK_GEN_PID > "$PID_DIR/task_generator.pid"
echo -e "    ${GREEN}✓ Task Generator (PID: $TASK_GEN_PID)${NC}"

sleep 2

# 4.2 LLM Scheduler
echo "  → 启动 LLM Scheduler..."
nohup python scripts/start_scheduler.py > "$LOG_DIR/scheduler.log" 2>&1 &
SCHEDULER_PID=$!
echo $SCHEDULER_PID > "$PID_DIR/scheduler.pid"
echo -e "    ${GREEN}✓ LLM Scheduler (PID: $SCHEDULER_PID)${NC}"

sleep 2

# 4.3 Result Aggregator
echo "  → 启动 Result Aggregator..."
nohup python scripts/start_result_aggregator.py > "$LOG_DIR/result_aggregator.log" 2>&1 &
AGGREGATOR_PID=$!
echo $AGGREGATOR_PID > "$PID_DIR/result_aggregator.pid"
echo -e "    ${GREEN}✓ Result Aggregator (PID: $AGGREGATOR_PID)${NC}"

echo -e "${GREEN}✓ 所有流式服务启动成功${NC}"
echo ""

###############################################################################
# Step 5: 启动 Flask 应用 (Kafka 模式)
###############################################################################
echo -e "${YELLOW}[Step 5/6]${NC} 启动 Flask 应用 (Kafka 流式模式)..."

export ALGO_ENABLE_KAFKA_STREAMING=true

nohup python app.py > "$LOG_DIR/flask_app.log" 2>&1 &
FLASK_PID=$!
echo $FLASK_PID > "$PID_DIR/flask_app.pid"
echo -e "${GREEN}✓ Flask 应用启动成功 (PID: $FLASK_PID)${NC}"
echo ""

###############################################################################
# Step 6: 验证服务状态
###############################################################################
echo -e "${YELLOW}[Step 6/6]${NC} 验证服务状态..."

echo "等待服务完全启动 (5秒)..."
sleep 5

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ 所有服务启动完成！${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

echo "📊 服务访问地址："
echo "  • Flask 应用:       http://localhost:5000"
echo "  • Prometheus 指标:  http://localhost:5000/metrics"
echo "  • Prometheus UI:    http://localhost:9100"
echo "  • Grafana:          http://localhost:3100 (admin/admin)"
echo ""

echo "📝 日志文件："
echo "  • Task Generator:   $LOG_DIR/task_generator.log"
echo "  • LLM Scheduler:    $LOG_DIR/scheduler.log"
echo "  • Result Aggregator: $LOG_DIR/result_aggregator.log"
echo "  • Flask App:        $LOG_DIR/flask_app.log"
echo ""

echo "📋 进程 PID："
echo "  • Task Generator:   $TASK_GEN_PID"
echo "  • LLM Scheduler:    $SCHEDULER_PID"
echo "  • Result Aggregator: $AGGREGATOR_PID"
echo "  • Flask App:        $FLASK_PID"
echo ""

echo "🛑 停止所有服务："
echo "  ./scripts/stop_all_streaming.sh"
echo ""

echo "💡 提示："
echo "  - 使用 'tail -f $LOG_DIR/task_generator.log' 查看实时日志"
echo "  - 使用 'docker ps' 查看基础设施容器状态"
echo "  - 使用 'ps aux | grep python' 查看 Python 进程状态"
echo ""

echo -e "${GREEN}✅ 启动完成！系统已准备就绪。${NC}"
