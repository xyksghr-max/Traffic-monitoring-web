#!/bin/bash

# 检查 Redis 中的关键数据

echo "======================================"
echo "Redis 数据检查工具"
echo "======================================"
echo ""

# 检查 Redis 是否可用
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis 不可用！"
    exit 1
fi

echo "✅ Redis 连接成功"
echo ""

# 检查 detection:* keys
echo "📥 检测数据 (detection:*)"
echo "--------------------------------------"
detection_count=$(redis-cli --scan --pattern "detection:*" | wc -l)
echo "总数: $detection_count"
if [ $detection_count -gt 0 ]; then
    echo "最近的 5 个:"
    redis-cli --scan --pattern "detection:*" | head -5 | while read key; do
        ttl=$(redis-cli ttl "$key")
        echo "  - $key (TTL: ${ttl}s)"
    done
fi
echo ""

# 检查 camera:*:latest keys
echo "📷 摄像头最新数据 (camera:*:latest)"
echo "--------------------------------------"
camera_count=$(redis-cli --scan --pattern "camera:*:latest" | wc -l)
echo "总数: $camera_count"
if [ $camera_count -gt 0 ]; then
    redis-cli --scan --pattern "camera:*:latest" | while read key; do
        ttl=$(redis-cli ttl "$key")
        data=$(redis-cli get "$key" | jq -r '.maxRiskLevel // "none"' 2>/dev/null || echo "N/A")
        echo "  - $key: risk=$data (TTL: ${ttl}s)"
    done
fi
echo ""

# 检查告警数据
echo "🚨 告警数据 (alerts:*)"
echo "--------------------------------------"
alert_count=$(redis-cli --scan --pattern "alerts:*" | wc -l)
echo "总数: $alert_count"
if [ $alert_count -gt 0 ]; then
    redis-cli --scan --pattern "alerts:*" | while read key; do
        count=$(redis-cli llen "$key")
        echo "  - $key: $count alerts"
    done
fi
echo ""

# 监听 WebSocket 发布 (10 秒)
echo "📡 监听 WebSocket 发布 (camera:*) - 10 秒"
echo "--------------------------------------"
timeout 10 redis-cli psubscribe "camera:*" || echo "未检测到发布消息"
echo ""

echo "======================================"
echo "检查完成"
echo "======================================"
