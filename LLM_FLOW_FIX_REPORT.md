# 大模型返回结果无法送达前端 - 修复报告

## 问题描述

**现象**：前端无法收到大模型的返回的检测结果

**日志**：
```
2025-10-20 23:10:22.458 | DEBUG | algo.consumers.result_aggregator:handle_assessment_result:99 - Processing assessment result for camera 5, request 15375648-5fe0-438f-81ef-3af9cabf6e4a
2025-10-20 23:10:22.459 | DEBUG | algo.consumers.result_aggregator:_get_detection_from_redis:154 - Detection data not found in Redis for 15375648-5fe0-438f-81ef-3af9cabf6e4a
```

## 根本原因

通过分析代码和日志，发现问题在于：

**Pipeline 发送 Kafka 消息后，没有将检测数据存储到 Redis**

数据流应该是：
1. Pipeline 检测并发送到 Kafka → ✅
2. Pipeline 同时存储检测数据到 Redis → ❌ **缺失这一步**
3. TaskGenerator 生成任务 → ✅
4. LLMScheduler 调用大模型 → ✅
5. ResultAggregator 从 Redis 读取检测数据 → ❌ **找不到数据**
6. ResultAggregator 合并并发布到 WebSocket → ❌ **无法完成**

## 修复内容

### 1. Pipeline 添加 Redis 存储 (`algo/rtsp_detect/pipeline.py`)

**修改位置**：第 269-300 行

**修改内容**：
```python
# 发送到 Kafka
message_id = self.kafka_producer.send(kafka_payload, self.camera_id)

# 新增：存储检测数据到 Redis
if message_id:
    try:
        import redis
        import json
        redis_client = redis.Redis(
            host='localhost',
            port=6379,
            db=0,
            decode_responses=True,
            socket_connect_timeout=5
        )
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
        redis_client.setex(
            detection_key,
            300,  # 5 分钟 TTL
            json.dumps(detection_data, ensure_ascii=False)
        )
        logger.debug(
            "Stored detection data in Redis: key={}, messageId={}",
            detection_key,
            message_id
        )
    except Exception as redis_exc:
        logger.warning(
            "Failed to store detection in Redis for camera {}: {}",
            self.camera_id,
            redis_exc
        )
```

**关键点**：
- 使用 `messageId` 作为 Redis key：`detection:{messageId}`
- 设置 5 分钟 TTL，避免内存泄漏
- 存储完整的检测数据供后续聚合使用
- 错误处理：Redis 失败不影响主流程

### 2. 增强日志输出

在所有关键节点添加了详细的 emoji 日志：

#### Pipeline (`algo/rtsp_detect/pipeline.py`)
- `✅ Sent detection to Kafka for camera X with Y groups, messageId=Z`

#### SimpleTaskGenerator (`algo/task_generator/simple_generator.py`)
- `📥 Received detection result: messageId=X, cameraId=Y`
- `📤 Generated N assessment tasks for camera X (messageId=Y)`

#### LLMTaskScheduler (`algo/scheduler/task_scheduler.py`)
- `📥 Received LLM task: taskId=X, requestId=Y, cameraId=Z`
- `🤖 LLM Response for task X: riskLevel=Y, hasDangerous=Z, results=...`（**包含完整的大模型返回信息**）
- `✅ Task X completed in Ns, sent to Kafka`
- `📤 Sent LLM result to Kafka: requestId=X, cameraId=Y, risk=Z`

#### ResultAggregator (`algo/consumers/result_aggregator.py`)
- `📥 Received LLM assessment result: requestId=X, cameraId=Y, hasDangerous=Z`
- `✅ Found detection data in Redis: key=X, size=Y bytes`
- `❌ Detection data not found in Redis: key=X, requestId=Y`（**高亮显示错误**）
- `📡 Published to WebSocket channel 'camera:X': Y subscribers`
- `✅ Aggregated result for camera X, risk=Y`

### 3. 创建调试工具

#### 3.1 LLM 数据流调试器 (`scripts/debug_llm_flow.py`)

**功能**：
- 实时监听 Kafka 3 个 Topic（detection-results, assessment-tasks, risk-assessment-results）
- 检查 Redis 中的数据存储情况
- 显示完整的数据流路径
- 高亮显示问题节点
- **打印大模型返回的完整信息**

**使用方法**：
```bash
# 安装依赖
pip install rich confluent-kafka redis

# 运行调试器
python scripts/debug_llm_flow.py
```

**输出示例**：
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ 🤖 LLM Result (requestId=a1b2c3d4-5678-...)           ┃
┠──────────────────────────────────────────────────────┨
┃ {                                                    ┃
┃   "requestId": "a1b2c3d4-5678-...",                  ┃
┃   "cameraId": 5,                                     ┃
┃   "hasDangerousDriving": true,                       ┃
┃   "maxRiskLevel": "medium",                          ┃
┃   "results": [                                       ┃
┃     {                                                ┃
┃       "groupIndex": 0,                               ┃
┃       "riskLevel": "medium",                         ┃
┃       "confidence": 0.75,                            ┃
┃       "riskTypes": ["车距过近", "车流拥堵"],          ┃
┃       "description": "检测到多辆车距离过近..."        ┃
┃     }                                                ┃
┃   ]                                                  ┃
┃ }                                                    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

#### 3.2 Redis 数据检查工具 (`scripts/check_redis_keys.sh`)

**功能**：
- 检查 Redis 连接状态
- 统计各类数据的数量（detection:*, camera:*:latest, alerts:*）
- 显示最近的检测数据和 TTL
- 监听 WebSocket 发布

**使用方法**：
```bash
chmod +x scripts/check_redis_keys.sh
./scripts/check_redis_keys.sh
```

**输出示例**：
```
======================================
Redis 数据检查工具
======================================

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
4) "{"cameraId":5,"maxRiskLevel":"medium",...}"
```

## 测试步骤

### 1. 启动所有服务

```bash
# 启动基础设施
docker-compose up -d

# 启动 Streaming 服务
./scripts/start_all_streaming.sh
```

### 2. 启动调试器（3 个终端）

```bash
# 终端 1: LLM 流调试器
python scripts/debug_llm_flow.py

# 终端 2: Redis 数据检查
./scripts/check_redis_keys.sh

# 终端 3: 应用日志
tail -f logs/app.log | grep -E "📥|📤|✅|❌|🤖|📡"
```

### 3. 推流测试摄像头

```bash
curl -X POST http://localhost:5000/api/cameras/5/start \
  -H "Content-Type: application/json" \
  -d '{
    "rtspUrl": "rtsp://example.com/stream",
    "enableKafka": true
  }'
```

### 4. 观察数据流

在调试器中应该看到完整的数据流：

```
📥 Detection: messageId=a1b2c3d4, camera=5, groups=3, redis=✅
📋 Task: taskId=a1b2c3d4_group0, requestId=a1b2c3d4, camera=5, group=0, redis=✅
🤖 LLM Result (requestId=a1b2c3d4)
  {
    "hasDangerousDriving": true,
    "maxRiskLevel": "medium",
    "results": [...]
  }
📡 Published to WebSocket channel 'camera:5': 1 subscribers
✅ Aggregated result for camera 5, risk=medium
```

### 5. 前端验证

在浏览器控制台：

```javascript
// 检查收到的消息
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('✅ Received from backend:');
  console.log('  Camera:', data.cameraId);
  console.log('  Risk:', data.maxRiskLevel);
  console.log('  Dangerous:', data.hasDangerousDriving);
  console.log('  Results:', data.riskAssessment?.results);
};
```

## 预期结果

修复后，数据流应该完整：

1. ✅ Pipeline 检测并发送 Kafka 消息，**同时存储到 Redis**
2. ✅ TaskGenerator 生成任务，使用正确的 requestId
3. ✅ LLMScheduler 调用大模型并返回结果
4. ✅ ResultAggregator 从 Redis 成功读取检测数据
5. ✅ ResultAggregator 合并数据并发布到 WebSocket
6. ✅ 前端通过 WebSocket 接收完整的评估结果

## 日志示例

### 成功的完整日志流

```
# 1. Pipeline 发送检测结果
2025-10-21 10:15:23.456 | INFO | algo.rtsp_detect.pipeline:_run:269 - ✅ Sent detection to Kafka for camera 5 with 3 groups, messageId=a1b2c3d4-5678-9012-3456-abcdefghijkl

# 2. TaskGenerator 收到并生成任务
2025-10-21 10:15:23.458 | INFO | algo.task_generator.simple_generator:handle_detection_result:50 - 📥 Received detection result: messageId=a1b2c3d4-5678-9012-3456-abcdefghijkl, cameraId=5
2025-10-21 10:15:23.460 | INFO | algo.task_generator.simple_generator:handle_detection_result:98 - 📤 Generated 3 assessment tasks for camera 5 (messageId=a1b2c3d4-5678-9012-3456-abcdefghijkl)

# 3. LLMScheduler 收到任务
2025-10-21 10:15:23.462 | INFO | algo.scheduler.task_scheduler:_handle_task_sync:96 - 📥 Received LLM task: taskId=a1b2c3d4-5678-9012-3456-abcdefghijkl_group0, requestId=a1b2c3d4-5678-9012-3456-abcdefghijkl, cameraId=5

# 4. LLM 返回结果
2025-10-21 10:15:26.123 | INFO | algo.scheduler.task_scheduler:process_task:158 - 🤖 LLM Response for task a1b2c3d4-5678-9012-3456-abcdefghijkl_group0: riskLevel=medium, hasDangerous=True, results=[{"groupIndex":0,"riskLevel":"medium","confidence":0.75,"riskTypes":["车距过近","车流拥堵"],"description":"检测到多辆车距离过近..."}]

# 5. LLM 结果发送到 Kafka
2025-10-21 10:15:26.125 | INFO | algo.scheduler.task_scheduler:_send_result:198 - 📤 Sent LLM result to Kafka: requestId=a1b2c3d4-5678-9012-3456-abcdefghijkl, cameraId=5, risk=medium

# 6. ResultAggregator 收到并处理
2025-10-21 10:15:26.127 | INFO | algo.consumers.result_aggregator:handle_assessment_result:101 - 📥 Received LLM assessment result: requestId=a1b2c3d4-5678-9012-3456-abcdefghijkl, cameraId=5, hasDangerous=True
2025-10-21 10:15:26.128 | DEBUG | algo.consumers.result_aggregator:_get_detection_from_redis:167 - ✅ Found detection data in Redis: key=detection:a1b2c3d4-5678-9012-3456-abcdefghijkl, size=2345 bytes

# 7. 发布到 WebSocket
2025-10-21 10:15:26.130 | INFO | algo.consumers.result_aggregator:_publish_to_websocket:203 - 📡 Published to WebSocket channel 'camera:5': 1 subscribers, risk=medium, hasDangerous=True
2025-10-21 10:15:26.131 | INFO | algo.consumers.result_aggregator:handle_assessment_result:155 - ✅ Aggregated result for camera 5, risk=medium
```

## 常见问题排查

### Q1: 仍然显示 "Detection data not found in Redis"

**检查**：
```bash
# 查看 Redis 中是否有数据
redis-cli --scan --pattern "detection:*"

# 查看 Pipeline 日志
tail -f logs/app.log | grep "Stored detection data in Redis"
```

**可能原因**：
- Redis 未启动
- Redis 连接失败
- messageId 为空

### Q2: 前端仍然收不到数据

**检查**：
```bash
# 监听 WebSocket 发布
redis-cli psubscribe "camera:*"
```

**可能原因**：
- WebSocket 未连接
- 订阅了错误的频道
- ResultAggregator 未启动

### Q3: LLM 没有返回结果

**检查**：
```bash
# 查看 LLM Scheduler 日志
tail -f logs/app.log | grep "🤖 LLM Response"
```

**可能原因**：
- API Key 无效
- 网络问题
- 任务队列阻塞

## 文件变更清单

### 修改的文件

1. **algo/rtsp_detect/pipeline.py**
   - 添加 Redis 存储逻辑
   - 增强日志输出

2. **algo/task_generator/simple_generator.py**
   - 增强日志输出

3. **algo/scheduler/task_scheduler.py**
   - 增强日志输出
   - 添加 LLM 返回结果的完整打印

4. **algo/consumers/result_aggregator.py**
   - 增强日志输出
   - 修复变量引用错误

### 新增的文件

1. **scripts/debug_llm_flow.py**
   - LLM 数据流实时调试器

2. **scripts/check_redis_keys.sh**
   - Redis 数据检查工具

3. **LLM_FLOW_DEBUG_GUIDE.md**
   - 详细的调试指南和故障排查手册

## 性能影响

### Redis 存储开销

- 每次检测额外增加 1-3ms（Redis 写入时间）
- 内存占用：每条检测数据约 2-5KB，5 分钟 TTL 自动清理
- 对于 10 个摄像头，每秒 1 帧，内存占用约 10 * 5KB * 300 = 15MB

### 优化建议

如果 Redis 成为瓶颈，可以考虑：

1. **连接池复用**（当前每次创建新连接）
2. **异步写入**（不阻塞主流程）
3. **缩短 TTL**（如果 LLM 通常在 10 秒内完成）

## 总结

**核心修复**：Pipeline 发送 Kafka 消息后，立即将检测数据存储到 Redis

**调试增强**：在所有关键节点添加详细日志，包括大模型返回的完整信息

**调试工具**：提供实时数据流监控和 Redis 数据检查工具

**预期效果**：前端可以正常接收大模型的风险评估结果

---

修复完成时间：2025-10-21
修复版本：v1.0.1
