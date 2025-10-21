# 大模型数据流调试指南

## 问题诊断

前端无法收到大模型返回的检测结果，可能的原因：

### 1. 数据流路径

完整的数据流应该是：

```
Pipeline (检测) 
  ↓ Kafka: detection-results
  ↓ (同时存储到 Redis: detection:{messageId})
  ↓
SimpleTaskGenerator (任务生成)
  ↓ Kafka: assessment-tasks
  ↓
LLMTaskScheduler (大模型评估)
  ↓ Kafka: risk-assessment-results
  ↓
ResultAggregator (结果聚合)
  ↓ 从 Redis 读取: detection:{requestId}
  ↓ 合并数据
  ↓ Redis Pub/Sub: camera:{cameraId}
  ↓
前端 WebSocket 订阅
```

### 2. 问题定位

根据日志 `Detection data not found in Redis for {requestId}`，问题出在：

**原因**：Pipeline 发送 Kafka 消息后，没有将检测数据存储到 Redis

**影响**：ResultAggregator 无法从 Redis 获取原始检测数据，导致前端收不到完整结果

## 修复内容

### 1. Pipeline 修复 (`algo/rtsp_detect/pipeline.py`)

**修改点**：
- 在发送 Kafka 消息后，立即将检测数据存储到 Redis
- 使用 `messageId` 作为 key：`detection:{messageId}`
- 设置 5 分钟 TTL
- 存储内容包括：检测对象、交通群组、图像信息等

**关键代码**：
```python
message_id = self.kafka_producer.send(kafka_payload, self.camera_id)

if message_id:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    detection_key = f"detection:{message_id}"
    detection_data = {
        "cameraId": self.camera_id,
        "timestamp": kafka_payload["timestamp"],
        "detectedObjects": detected_objects,
        "trafficGroups": normalized_groups,
        "groupImages": group_images,
        "imageWidth": width,
        "imageHeight": height,
        "messageId": message_id,
    }
    redis_client.setex(detection_key, 300, json.dumps(detection_data))
```

### 2. 日志增强

在所有关键节点添加了详细的日志输出：

#### Pipeline
- `✅ Sent detection to Kafka for camera X with Y groups, messageId=Z`

#### SimpleTaskGenerator
- `📥 Received detection result: messageId=X, cameraId=Y`
- `📤 Generated N assessment tasks for camera X (messageId=Y)`

#### LLMTaskScheduler
- `📥 Received LLM task: taskId=X, requestId=Y, cameraId=Z`
- `🤖 LLM Response for task X: riskLevel=Y, hasDangerous=Z, results=...`
- `✅ Task X completed in Ns, sent to Kafka`
- `📤 Sent LLM result to Kafka: requestId=X, cameraId=Y, risk=Z`

#### ResultAggregator
- `📥 Received LLM assessment result: requestId=X, cameraId=Y, hasDangerous=Z`
- `✅ Found detection data in Redis: key=X, size=Y bytes`
- `❌ Detection data not found in Redis: key=X, requestId=Y`
- `📡 Published to WebSocket channel 'camera:X': Y subscribers`
- `✅ Aggregated result for camera X, risk=Y`

## 调试工具

### 1. LLM 数据流调试器

**文件**: `scripts/debug_llm_flow.py`

**功能**：
- 实时监听 Kafka 3 个 Topic（检测结果、评估任务、LLM 结果）
- 检查 Redis 中的数据存储情况
- 显示完整的数据流路径
- 高亮显示问题节点
- 打印 LLM 返回的完整信息

**使用方法**：
```bash
# 安装依赖（如需要）
pip install rich

# 运行调试器
python scripts/debug_llm_flow.py
```

**输出示例**：
```
📊 Statistics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Detections Received        12
Tasks Generated           36
LLM Results Received       8
Redis Stored              12
Redis Not Found            0

📥 Recent Detections
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Time     MessageID  Camera  Groups  Redis
14:23:15 a1b2c3d4   5       3       ✅
14:23:16 e5f6g7h8   5       2       ✅

📋 Recent Tasks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Time     TaskID      RequestID  Camera  Group  Redis
14:23:15 a1b2c3d4_g0 a1b2c3d4   5       0      ✅
14:23:15 a1b2c3d4_g1 a1b2c3d4   5       1      ✅

🤖 Recent LLM Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Time     RequestID  Camera  Risk    Dangerous  Results  Redis
14:23:18 a1b2c3d4   5       medium  ✅         2        ✅
```

### 2. Redis 数据检查工具

**文件**: `scripts/check_redis_keys.sh`

**功能**：
- 检查 Redis 连接状态
- 统计各类数据的数量
- 显示最近的检测数据
- 显示摄像头最新数据
- 显示告警数据
- 监听 WebSocket 发布

**使用方法**：
```bash
chmod +x scripts/check_redis_keys.sh
./scripts/check_redis_keys.sh
```

**输出示例**：
```
✅ Redis 连接成功

📥 检测数据 (detection:*)
--------------------------------------
总数: 5
最近的 5 个:
  - detection:a1b2c3d4-5678-... (TTL: 287s)
  - detection:e5f6g7h8-9012-... (TTL: 283s)

📷 摄像头最新数据 (camera:*:latest)
--------------------------------------
总数: 2
  - camera:5:latest: risk=medium (TTL: 298s)
  - camera:6:latest: risk=none (TTL: 295s)

📡 监听 WebSocket 发布 (camera:*) - 10 秒
--------------------------------------
1) "pmessage"
2) "camera:*"
3) "camera:5"
4) "{\"cameraId\":5,\"maxRiskLevel\":\"medium\",...}"
```

## 测试步骤

### 1. 启动所有服务

```bash
# 启动基础设施
docker-compose up -d

# 启动 Streaming 服务
./scripts/start_all_streaming.sh
```

### 2. 运行调试器

```bash
# 终端 1: 运行 LLM 流调试器
python scripts/debug_llm_flow.py

# 终端 2: 检查 Redis 数据
./scripts/check_redis_keys.sh

# 终端 3: 查看应用日志
tail -f logs/app.log
```

### 3. 推流测试摄像头

```bash
# 使用测试脚本推流
curl -X POST http://localhost:5000/api/cameras/5/start \
  -H "Content-Type: application/json" \
  -d '{
    "rtspUrl": "rtsp://example.com/stream",
    "enableKafka": true
  }'
```

### 4. 观察数据流

在调试器中应该看到：

1. **检测结果** (detection-results topic)
   - messageId 生成
   - Redis 存储成功 ✅

2. **评估任务** (assessment-tasks topic)
   - requestId = messageId
   - Redis 中检测数据存在 ✅

3. **LLM 结果** (risk-assessment-results topic)
   - 包含完整的风险评估信息
   - Redis 中检测数据存在 ✅

4. **WebSocket 发布** (camera:{cameraId} channel)
   - 订阅者数量 > 0
   - 包含合并后的完整数据

### 5. 前端检查

在浏览器控制台中：

```javascript
// 检查 WebSocket 连接
console.log('WebSocket state:', ws.readyState);

// 检查收到的消息
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
  console.log('Risk level:', data.maxRiskLevel);
  console.log('Has dangerous:', data.hasDangerousDriving);
  console.log('Results:', data.riskAssessment?.results);
};
```

## 常见问题排查

### Q1: Redis 中没有 detection:* 数据

**检查**：
```bash
redis-cli --scan --pattern "detection:*"
```

**原因**：
- Pipeline 没有启用 Kafka 模式
- Redis 连接失败
- messageId 为空

**解决**：
- 检查 `enableKafka=true`
- 查看 Pipeline 日志中的 Redis 错误
- 确认 Kafka Producer 返回了 messageId

### Q2: LLM 结果中 requestId 与 messageId 不匹配

**检查**：
```bash
# 查看 Kafka 消息
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic assessment-tasks --from-beginning | grep requestId
```

**原因**：
- SimpleTaskGenerator 传递了错误的 requestId

**解决**：
- 确认修复已应用
- 重启 SimpleTaskGenerator

### Q3: ResultAggregator 报告 "Detection data not found"

**检查**：
1. 查看日志中的 requestId
2. 检查 Redis 是否有对应的 key
3. 检查 TTL 是否已过期

**解决**：
```bash
# 查看具体的 key
redis-cli get "detection:{requestId}"

# 如果不存在，检查所有 detection:* keys
redis-cli --scan --pattern "detection:*"

# 检查 TTL
redis-cli ttl "detection:{requestId}"
```

### Q4: WebSocket 没有订阅者

**检查**：
```bash
# 监听 WebSocket 发布
redis-cli psubscribe "camera:*"
```

**原因**：
- 前端未连接 WebSocket
- WebSocket 订阅了错误的频道

**解决**：
- 检查前端 WebSocket 连接状态
- 确认订阅的频道名称正确：`camera:{cameraId}`

## 性能优化建议

### 1. Redis 连接复用

当前每次存储都创建新的 Redis 连接，建议改为连接池：

```python
# 在 Pipeline __init__ 中
if self.enable_kafka:
    self.redis_client = redis.Redis(...)
```

### 2. 批量存储

如果检测频率很高，考虑批量写入 Redis：

```python
# 使用 pipeline
pipe = redis_client.pipeline()
for i in range(10):
    pipe.setex(f"detection:{msg_id}", 300, data)
pipe.execute()
```

### 3. TTL 优化

根据实际 LLM 处理时间调整 TTL：
- 当前：5 分钟（300 秒）
- 如果 LLM 通常在 10 秒内完成，可以减少到 60 秒

## 监控指标

建议添加以下 Prometheus 指标：

```python
# Redis 存储成功/失败
redis_storage_total = Counter('redis_storage_total', 'Redis storage operations', ['status'])

# Redis 查询成功/失败
redis_query_total = Counter('redis_query_total', 'Redis query operations', ['status'])

# WebSocket 发布订阅者数量
websocket_subscribers = Gauge('websocket_subscribers', 'WebSocket subscribers', ['camera_id'])
```

## 日志级别调整

如果日志太多，可以调整级别：

```python
# config.py
LOGGING_LEVEL = "INFO"  # 或 "WARNING" 减少输出

# 仅调试特定模块
loguru_config = {
    "handlers": [
        {"sink": "logs/llm_flow.log", "level": "DEBUG", "filter": lambda record: "llm" in record["name"].lower()},
        {"sink": "logs/app.log", "level": "INFO"},
    ]
}
```

## 总结

修复后的数据流：

1. ✅ Pipeline 发送 Kafka 消息并存储到 Redis
2. ✅ SimpleTaskGenerator 使用正确的 requestId
3. ✅ LLMTaskScheduler 输出完整的 LLM 响应
4. ✅ ResultAggregator 从 Redis 读取检测数据并发布到 WebSocket
5. ✅ 前端通过 WebSocket 接收完整的评估结果

所有关键节点都有详细的日志输出，方便调试和监控。
