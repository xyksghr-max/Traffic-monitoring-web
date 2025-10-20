# 前端只显示 "none" 风险级别问题诊断指南

## 问题描述
前端显示的风险级别只有 "none"，没有大模型评估的风险信息。

## 可能原因分析

### 1. 数据流向图
```
检测结果 → Task Generator → LLM Scheduler → Result Aggregator → WebSocket → 前端
   ↓            ↓                ↓                ↓                ↓
Redis     Kafka Topic      Kafka Topic      Kafka Topic       Redis Pub/Sub
         detection-    → assessment-    → risk-assessment- →  camera:{id}
         results           tasks             results
```

### 2. 常见问题点

#### A. Kafka 流式模式未启用
**症状**: 检测结果有，但没发送给大模型

**检查方法**:
```bash
# 1. 检查环境变量
echo $ALGO_ENABLE_KAFKA_STREAMING

# 2. 检查 Flask 应用启动日志
grep -i "kafka" logs/streaming/flask_app.log

# 3. 检查是否有 Kafka producer
grep -i "Kafka producer initialized" logs/streaming/flask_app.log
```

**解决方案**:
- 确保启动时设置了环境变量: `ALGO_ENABLE_KAFKA_STREAMING=true`
- 重启 Flask 应用

---

#### B. Kafka 服务未启动
**症状**: 无法发送/接收消息

**检查方法**:
```bash
# 检查 Kafka 容器状态
docker ps | grep kafka

# 检查 Kafka 端口
netstat -an | grep 9092  # Linux
Get-NetTCPConnection -LocalPort 9092  # PowerShell
```

**解决方案**:
```bash
# 启动基础设施
cd deployment
docker-compose -f docker-compose.infra.yml up -d

# 检查日志
docker-compose -f docker-compose.infra.yml logs kafka
```

---

#### C. Kafka Topics 未创建
**症状**: 消息发送失败或消费不到

**检查方法**:
```bash
# 列出所有 topics
docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092

# 应该看到这三个 topics:
# - detection-results
# - assessment-tasks
# - risk-assessment-results
```

**解决方案**:
```bash
# 初始化 topics
python scripts/init_kafka_topics.py
```

---

#### D. 流式处理服务未启动
**症状**: Topic 有数据但没处理

**需要的三个服务**:
1. **Task Generator**: 消费 `detection-results` → 生产 `assessment-tasks`
2. **LLM Scheduler**: 消费 `assessment-tasks` → 调用大模型 → 生产 `risk-assessment-results`
3. **Result Aggregator**: 消费 `risk-assessment-results` → 发布到 WebSocket

**检查方法**:
```bash
# 检查进程是否运行 (Linux/Mac)
ps aux | grep -E "task_generator|scheduler|result_aggregator"

# 检查进程是否运行 (Windows PowerShell)
Get-Process python | Where-Object {$_.CommandLine -like "*task_generator*"}
Get-Process python | Where-Object {$_.CommandLine -like "*scheduler*"}
Get-Process python | Where-Object {$_.CommandLine -like "*result_aggregator*"}

# 检查日志
tail -f logs/streaming/task_generator.log
tail -f logs/streaming/scheduler.log
tail -f logs/streaming/result_aggregator.log
```

**解决方案**:
```bash
# Linux/Mac
./scripts/start_all_streaming.sh

# Windows (PowerShell)
.\scripts\start_all_streaming.ps1

# Windows (CMD)
scripts\start_all_streaming.bat
```

---

#### E. API Key 未配置或无效
**症状**: Scheduler 无法调用大模型

**检查方法**:
```bash
# 检查 API Key 配置
cat config/api_keys.yaml

# 验证 API Key
python scripts/verify_api_keys.py

# 查看 scheduler 日志中的错误
grep -i "api" logs/streaming/scheduler.log
grep -i "error" logs/streaming/scheduler.log
```

**关键日志特征**:
- `Failed to acquire API key`: Key 池没有可用的 key
- `API call failed: HTTP 401`: Key 无效
- `API call failed: HTTP 429`: 超过速率限制

**解决方案**:
```yaml
# 编辑 config/api_keys.yaml
api_keys:
  - key_id: "key-1"
    key: "sk-your-actual-dashscope-api-key"
    enabled: true
    max_rpm: 10
    max_tpm: 50000
```

---

#### F. 大模型调用超时或失败
**症状**: Scheduler 调用大模型但返回空结果

**检查日志**:
```bash
# 查看 scheduler 日志
tail -n 100 logs/streaming/scheduler.log | grep -E "timeout|failed|error"
```

**关键日志**:
- `LLM API timeout`: 网络超时
- `Failed to parse LLM response`: 大模型返回格式错误
- `Rate limit hit`: 触发速率限制

**解决方案**:
1. 增加超时时间（在 `scripts/start_scheduler.py` 中）
2. 检查网络连接
3. 检查 API Key 配额

---

#### G. Result Aggregator 未正确聚合
**症状**: 有评估结果但没发送到前端

**检查方法**:
```bash
# 查看 aggregator 日志
tail -f logs/streaming/result_aggregator.log

# 应该看到类似信息:
# "Aggregated result for camera X, risk=high/medium/low"
```

**检查 Redis 连接**:
```bash
# 测试 Redis
docker exec -it redis redis-cli ping
# 应该返回: PONG

# 查看 Redis 发布的消息
docker exec -it redis redis-cli
> SUBSCRIBE camera:*
```

---

#### H. WebSocket 未订阅 Redis
**症状**: 数据到 Redis 了但前端收不到

**检查方法**:
```bash
# 查看 Flask 日志
tail -f logs/streaming/flask_app.log | grep -i websocket
```

**注意**: 在流式模式下，WebSocket **不直接接收检测结果**，而是从 Redis Pub/Sub 订阅。

---

## 快速诊断步骤

### 1. 检查完整数据流
```bash
# 监控所有 Kafka topics
docker exec -it kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic detection-results \
  --from-beginning

docker exec -it kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic assessment-tasks \
  --from-beginning

docker exec -it kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic risk-assessment-results \
  --from-beginning
```

### 2. 检查每个环节
```bash
# Step 1: 检测结果是否发送到 Kafka
# 应该看到: detection-results topic 有消息

# Step 2: Task Generator 是否生成任务
# 应该看到: assessment-tasks topic 有消息

# Step 3: LLM Scheduler 是否调用成功
# 应该看到: risk-assessment-results topic 有消息

# Step 4: Result Aggregator 是否聚合
# 应该看到: aggregator 日志中有 "Aggregated result"

# Step 5: Redis 是否发布
# 应该看到: Redis SUBSCRIBE camera:* 有消息
```

### 3. 最常见的问题
根据经验，最常见的是以下情况：

**问题 1**: 环境变量未设置
```bash
# 确保启动 Flask 时设置了
export ALGO_ENABLE_KAFKA_STREAMING=true  # Linux/Mac
$env:ALGO_ENABLE_KAFKA_STREAMING="true"  # PowerShell
```

**问题 2**: 服务未全部启动
```bash
# 必须同时运行这 4 个服务:
# 1. Flask App (app.py)
# 2. Task Generator (scripts/start_task_generator.py)
# 3. LLM Scheduler (scripts/start_scheduler.py)
# 4. Result Aggregator (scripts/start_result_aggregator.py)
```

**问题 3**: API Key 未配置
```bash
# 检查并配置
python scripts/verify_api_keys.py
```

---

## 调试脚本

### 检查当前状态
```bash
#!/bin/bash
echo "=== Kafka 状态 ==="
docker ps | grep kafka

echo -e "\n=== Kafka Topics ==="
docker exec kafka kafka-topics --list --bootstrap-server localhost:9092

echo -e "\n=== Python 进程 ==="
ps aux | grep -E "task_generator|scheduler|result_aggregator|app.py" | grep -v grep

echo -e "\n=== 最新日志 ==="
echo "--- Task Generator ---"
tail -n 5 logs/streaming/task_generator.log

echo -e "\n--- Scheduler ---"
tail -n 5 logs/streaming/scheduler.log

echo -e "\n--- Aggregator ---"
tail -n 5 logs/streaming/result_aggregator.log
```

### PowerShell 版本
```powershell
Write-Host "=== Kafka 状态 ===" -ForegroundColor Cyan
docker ps | Select-String kafka

Write-Host "`n=== Kafka Topics ===" -ForegroundColor Cyan
docker exec kafka kafka-topics --list --bootstrap-server localhost:9092

Write-Host "`n=== Python 进程 ===" -ForegroundColor Cyan
Get-Process python | Where-Object {
    $_.CommandLine -like "*task_generator*" -or
    $_.CommandLine -like "*scheduler*" -or
    $_.CommandLine -like "*result_aggregator*" -or
    $_.CommandLine -like "*app.py*"
}

Write-Host "`n=== 最新日志 ===" -ForegroundColor Cyan
Write-Host "--- Task Generator ---"
Get-Content logs\streaming\task_generator.log -Tail 5

Write-Host "`n--- Scheduler ---"
Get-Content logs\streaming\scheduler.log -Tail 5

Write-Host "`n--- Aggregator ---"
Get-Content logs\streaming\result_aggregator.log -Tail 5
```

---

## 解决方案总结

### 方案 1: 完整重启（最彻底）
```bash
# 1. 停止所有服务
./scripts/stop_all_streaming.sh  # 或 .bat / .ps1

# 2. 重启基础设施
cd deployment
docker-compose -f docker-compose.infra.yml down
docker-compose -f docker-compose.infra.yml up -d
cd ..

# 3. 等待服务就绪
sleep 10

# 4. 初始化 Topics
python scripts/init_kafka_topics.py

# 5. 启动所有服务
./scripts/start_all_streaming.sh  # 或 .bat / .ps1
```

### 方案 2: 检查并修复特定问题
根据上面的诊断步骤，找到具体问题点进行修复。

---

## 验证修复

### 1. 检查日志是否正常
```bash
# 应该看到类似输出:
# Task Generator: "Generated X assessment tasks for camera Y"
# Scheduler: "Task task_id completed successfully in X.XXs"
# Aggregator: "Aggregated result for camera X, risk=high/medium/low"
```

### 2. 监控 Kafka 消息流
```bash
# 在三个终端分别运行:
# Terminal 1
docker exec -it kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic detection-results

# Terminal 2
docker exec -it kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic assessment-tasks

# Terminal 3
docker exec -it kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic risk-assessment-results
```

### 3. 测试前端
打开浏览器开发者工具，查看 WebSocket 消息，应该能看到包含 `riskAssessment` 字段的消息，其中 `maxRiskLevel` 不再是 "none"。

---

## 联系信息
如果问题仍未解决，请提供以下信息：
1. 所有服务的日志文件
2. `docker ps` 输出
3. Kafka topics 列表
4. 环境变量设置
5. 前端 WebSocket 接收到的消息示例
