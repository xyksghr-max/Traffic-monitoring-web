#!/bin/bash
###############################################################################
# 停止所有流式处理服务
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

PID_DIR="$ROOT_DIR/logs/pids"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              停止所有流式处理服务                             ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

###############################################################################
# Step 1: 停止 Python 进程
###############################################################################
echo -e "${YELLOW}[Step 1/2]${NC} 停止 Python 流式服务..."

stop_process() {
    local name=$1
    local pid_file="$PID_DIR/$2.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "  → 停止 $name (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            sleep 1
            
            # 如果进程仍在运行，强制杀死
            if kill -0 "$pid" 2>/dev/null; then
                echo "    使用 SIGKILL 强制停止..."
                kill -9 "$pid" 2>/dev/null || true
            fi
            echo -e "    ${GREEN}✓ $name 已停止${NC}"
        else
            echo -e "    ${YELLOW}⚠ $name 进程不存在 (PID: $pid)${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "    ${YELLOW}⚠ $name PID 文件不存在${NC}"
    fi
}

stop_process "Flask App" "flask_app"
stop_process "Result Aggregator" "result_aggregator"
stop_process "LLM Scheduler" "scheduler"
stop_process "Task Generator" "task_generator"

echo -e "${GREEN}✓ 所有 Python 服务已停止${NC}"
echo ""

###############################################################################
# Step 2: 停止 Docker 基础设施
###############################################################################
echo -e "${YELLOW}[Step 2/2]${NC} 停止基础设施 (Docker)..."

if [ -f "deployment/docker-compose.infra.yml" ]; then
    cd deployment
    docker-compose -f docker-compose.infra.yml down
    cd ..
    echo -e "${GREEN}✓ 基础设施已停止${NC}"
else
    echo -e "${YELLOW}⚠ deployment/docker-compose.infra.yml 不存在${NC}"
fi
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ 所有服务已停止${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

echo "💡 提示："
echo "  - 使用 'docker ps' 确认容器已停止"
echo "  - 使用 'ps aux | grep python' 确认进程已停止"
echo ""
