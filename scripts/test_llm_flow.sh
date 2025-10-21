#!/bin/bash

# 测试脚本：验证大模型数据流修复

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           大模型数据流修复 - 快速验证测试                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检查函数
check_service() {
    local service=$1
    local port=$2
    local name=$3
    
    if nc -z localhost $port 2>/dev/null; then
        echo -e "${GREEN}✅ $name (port $port)${NC}"
        return 0
    else
        echo -e "${RED}❌ $name (port $port) - 未运行${NC}"
        return 1
    fi
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "第 1 步：检查基础服务"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ALL_OK=true

check_service "kafka" 9092 "Kafka" || ALL_OK=false
check_service "redis" 6379 "Redis" || ALL_OK=false

if [ "$ALL_OK" = false ]; then
    echo ""
    echo -e "${YELLOW}⚠️  请先启动基础服务：${NC}"
    echo "  docker-compose up -d"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "第 2 步：检查 Redis 数据结构"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查 detection:* keys
DETECTION_COUNT=$(redis-cli --scan --pattern "detection:*" 2>/dev/null | wc -l)
echo -e "检测数据 (detection:*): ${BLUE}$DETECTION_COUNT${NC} 条"

# 检查 camera:*:latest keys
CAMERA_COUNT=$(redis-cli --scan --pattern "camera:*:latest" 2>/dev/null | wc -l)
echo -e "摄像头最新数据 (camera:*:latest): ${BLUE}$CAMERA_COUNT${NC} 条"

if [ $DETECTION_COUNT -gt 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Redis 中有检测数据，可以继续测试${NC}"
    echo ""
    echo "最近的检测数据示例："
    LATEST_KEY=$(redis-cli --scan --pattern "detection:*" 2>/dev/null | head -1)
    if [ -n "$LATEST_KEY" ]; then
        TTL=$(redis-cli ttl "$LATEST_KEY" 2>/dev/null)
        echo -e "  Key: ${BLUE}$LATEST_KEY${NC}"
        echo -e "  TTL: ${YELLOW}${TTL}s${NC}"
        echo ""
    fi
else
    echo ""
    echo -e "${YELLOW}⚠️  Redis 中暂无检测数据${NC}"
    echo "  这是正常的，如果还没有推流摄像头"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "第 3 步：检查 Kafka Topics"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

check_topic() {
    local topic=$1
    if kafka-topics --bootstrap-server localhost:9092 --list 2>/dev/null | grep -q "^$topic$"; then
        echo -e "${GREEN}✅ $topic${NC}"
        return 0
    else
        echo -e "${RED}❌ $topic - 不存在${NC}"
        return 1
    fi
}

check_topic "detection-results"
check_topic "assessment-tasks"
check_topic "risk-assessment-results"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "第 4 步：检查代码修复是否已应用"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查 Pipeline 是否有 Redis 存储代码
if grep -q "redis_client.setex" algo/rtsp_detect/pipeline.py; then
    echo -e "${GREEN}✅ Pipeline Redis 存储代码已添加${NC}"
else
    echo -e "${RED}❌ Pipeline Redis 存储代码未找到${NC}"
    echo "  请确认修复已应用"
fi

# 检查是否有增强的日志
if grep -q "📥\|📤\|🤖\|✅" algo/task_generator/simple_generator.py; then
    echo -e "${GREEN}✅ 增强日志输出已添加${NC}"
else
    echo -e "${YELLOW}⚠️  增强日志可能未完全应用${NC}"
fi

# 检查调试工具是否存在
if [ -f "scripts/debug_llm_flow.py" ]; then
    echo -e "${GREEN}✅ 调试工具 debug_llm_flow.py 已创建${NC}"
else
    echo -e "${RED}❌ 调试工具未找到${NC}"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "第 5 步：运行端到端测试（可选）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "如果要进行完整测试，请执行以下步骤："
echo ""
echo -e "${YELLOW}1. 启动 Streaming 服务：${NC}"
echo "   ./scripts/start_all_streaming.sh"
echo ""
echo -e "${YELLOW}2. 在新终端运行调试器：${NC}"
echo "   python scripts/debug_llm_flow.py"
echo ""
echo -e "${YELLOW}3. 在另一个终端推流摄像头：${NC}"
echo "   curl -X POST http://localhost:5000/api/cameras/5/start \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"rtspUrl\": \"rtsp://example.com/stream\", \"enableKafka\": true}'"
echo ""
echo -e "${YELLOW}4. 观察调试器输出，应该看到：${NC}"
echo "   📥 Detection: messageId=xxx, redis=✅"
echo "   📋 Task: requestId=xxx, redis=✅"
echo "   🤖 LLM Response: {...}"
echo "   📡 Published to WebSocket: X subscribers"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "测试完成"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${GREEN}✅ 基础检查通过${NC}"
echo ""
echo "详细文档："
echo "  - LLM_FLOW_DEBUG_GUIDE.md  (调试指南)"
echo "  - LLM_FLOW_FIX_REPORT.md   (修复报告)"
echo ""
