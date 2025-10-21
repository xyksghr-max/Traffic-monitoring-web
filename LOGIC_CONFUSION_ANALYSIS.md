# 数据流逻辑混淆问题分析

## 问题概述

在检查 `hasDangerousDriving` 和 `maxRiskLevel` 的使用时，发现了严重的**数据聚合逻辑错误**。

## 当前数据流架构

### 第 1 步：Pipeline 检测（1 个摄像头 → 多个群组）

```
Pipeline 检测结果：
{
  "cameraId": 5,
  "trafficGroups": [
    {"groupIndex": 0, "objectCount": 5},  // 群组 0
    {"groupIndex": 1, "objectCount": 3},  // 群组 1
    {"groupIndex": 2, "objectCount": 2}   // 群组 2
  ]
}
→ Kafka: detection-results (1 条消息，messageId=xxx)
```

### 第 2 步：TaskGenerator 生成任务（1 个检测 → 多个任务）

```python
# simple_generator.py 第 79-120 行
for group_image in group_images:
    task = {
        'taskId': f"{message_id}_group{group_index}",
        'requestId': message_id,  # ⚠️ 所有任务共享同一个 requestId
        'groupIndex': group_index,
        'groupImageBase64': ...
    }
    self.task_producer.send(task, camera_id)
```

**结果**：
- 输入：1 条检测消息（3 个群组）
- 输出：3 条任务消息
  - Task 1: requestId=xxx, groupIndex=0
  - Task 2: requestId=xxx, groupIndex=1
  - Task 3: requestId=xxx, groupIndex=2

### 第 3 步：LLMScheduler 处理任务（多个任务 → 多个结果）

```python
# task_scheduler.py 第 330-375 行
def _parse_llm_response(self, response: dict, task: Dict[str, Any]) -> Dict[str, Any]:
    # LLM 返回单个群组的评估
    parsed = {
        'riskLevel': 'medium',  // 该群组的风险等级
        'confidence': 0.75,
        ...
    }
    
    # ❌ 错误：将单个群组的风险等级作为整体风险
    return {
        'requestId': task.get('requestId'),  # xxx (3 个任务共享)
        'cameraId': 5,
        'results': [
            {
                'groupIndex': 0,
                'riskLevel': 'medium'
            }
        ],
        'hasDangerousDriving': parsed.get('riskLevel') != 'none',  # ❌ 错误
        'maxRiskLevel': parsed.get('riskLevel')                    # ❌ 错误
    }
```

**结果**：
- 输入：3 条任务
- 输出：3 条结果消息
  - Result 1: requestId=xxx, groupIndex=0, hasDangerous=true, maxRisk="low"
  - Result 2: requestId=xxx, groupIndex=1, hasDangerous=true, maxRisk="medium"
  - Result 3: requestId=xxx, groupIndex=2, hasDangerous=false, maxRisk="none"

**问题**：
- 每个结果都声称自己的 `maxRiskLevel` 是"最大风险"
- 但实际上只是该群组的风险等级
- 3 个结果都有相同的 `requestId=xxx`

### 第 4 步：ResultAggregator 合并结果（多个结果 → ？）

```python
# result_aggregator.py 第 95-155 行
def handle_assessment_result(self, result: Dict[str, Any]):
    request_id = result.get('requestId')  # xxx
    
    # ❌ 问题：每次只处理一个结果消息
    # 但同一个 requestId 会有 3 个结果消息
    
    detection_data = self._get_detection_from_redis(request_id)
    
    merged_result = {
        **detection_data,
        'riskAssessment': result,  # ⚠️ 只包含当前这个群组的结果
        'hasDangerousDriving': result.get('hasDangerousDriving', False),
        'maxRiskLevel': result.get('maxRiskLevel', 'none'),
    }
    
    # 发布到 WebSocket
    self._publish_to_websocket(camera_id, merged_result)
```

**结果**：
- 输入：3 条结果消息（requestId 相同）
- 输出：3 次 WebSocket 发布
  - Publish 1: risk="low", hasDangerous=true
  - Publish 2: risk="medium", hasDangerous=true
  - Publish 3: risk="none", hasDangerous=false

**问题**：
- 前端收到 3 次消息，每次内容不同
- 最后一次发布会覆盖前面的
- 无法准确反映整体风险情况

## 问题根源

### 问题 1：LLMScheduler 逻辑错误

**文件**：`algo/scheduler/task_scheduler.py` 第 372-373 行

```python
# ❌ 错误代码
'hasDangerousDriving': parsed.get('riskLevel', 'none') != 'none',
'maxRiskLevel': parsed.get('riskLevel', 'none'),
```

**问题**：
- `parsed` 是单个群组的大模型返回
- `hasDangerousDriving` 和 `maxRiskLevel` 应该是整体聚合结果
- 但当前逻辑将单个群组的风险等级直接作为整体风险

### 问题 2：ResultAggregator 未正确聚合

**文件**：`algo/consumers/result_aggregator.py` 第 95-155 行

**问题**：
- 每次只处理一个结果消息
- 没有将同一 `requestId` 的多个结果聚合
- 没有计算真正的 `maxRiskLevel`（所有群组中的最高风险）
- 没有正确判断 `hasDangerousDriving`（任一群组有风险即为 true）

## 正确的数据结构

### LLM Scheduler 应该返回（单个群组）

```json
{
  "requestId": "xxx",
  "cameraId": 5,
  "groupIndex": 0,           // ⚠️ 应该明确这是哪个群组的结果
  "results": [                // 该群组的评估结果
    {
      "groupIndex": 0,
      "riskLevel": "medium",  // 该群组的风险等级
      "confidence": 0.75,
      "riskTypes": ["车距过近"],
      "description": "..."
    }
  ],
  // ❌ 以下两个字段不应该在单个群组结果中
  "hasDangerousDriving": ???,  // 单个群组无法判断整体情况
  "maxRiskLevel": ???          // 单个群组不知道其他群组的风险
}
```

### Result Aggregator 应该返回（聚合所有群组）

```json
{
  "cameraId": 5,
  "timestamp": "...",
  "detectedObjects": [...],
  "trafficGroups": [...],
  "riskAssessment": {
    "allGroupResults": [       // 所有群组的结果
      {"groupIndex": 0, "riskLevel": "low", ...},
      {"groupIndex": 1, "riskLevel": "medium", ...},
      {"groupIndex": 2, "riskLevel": "none", ...}
    ]
  },
  "hasDangerousDriving": true,  // ✅ 聚合后：任一群组 != "none"
  "maxRiskLevel": "medium"      // ✅ 聚合后：最高风险等级
}
```

## 修复方案

### 方案 A：LLMScheduler 只返回群组级别信息（推荐）

**修改**：`algo/scheduler/task_scheduler.py`

```python
def _parse_llm_response(self, response: dict, task: Dict[str, Any]) -> Dict[str, Any]:
    # ... 解析 LLM 返回 ...
    
    # ✅ 修复：只返回该群组的结果，不做整体判断
    return {
        'requestId': task.get('requestId'),
        'cameraId': task.get('cameraId'),
        'timestamp': task.get('timestamp'),
        'groupIndex': task.get('groupIndex'),  # 明确标识群组
        'results': [
            {
                'groupIndex': task.get('groupIndex'),
                'riskLevel': parsed.get('riskLevel', 'none'),
                'confidence': float(parsed.get('confidence', 0.0)),
                'riskTypes': parsed.get('riskTypes', []),
                'description': parsed.get('description', ''),
                'dangerObjectCount': parsed.get('dangerObjectCount'),
                'triggerObjectIds': parsed.get('triggerObjectIds', []),
            }
        ],
        # ❌ 移除这两行（由 ResultAggregator 计算）
        # 'hasDangerousDriving': ...,
        # 'maxRiskLevel': ...,
    }
```

**修改**：`algo/consumers/result_aggregator.py`

```python
# 需要添加：聚合同一 requestId 的所有群组结果

import threading
from collections import defaultdict

class ResultAggregator:
    def __init__(self, ...):
        # 添加：按 requestId 聚合结果
        self.pending_results = defaultdict(list)  # {requestId: [result1, result2, ...]}
        self.result_locks = defaultdict(threading.Lock)  # {requestId: Lock}
        self.expected_groups = {}  # {requestId: expected_count}
        
    def handle_assessment_result(self, result: Dict[str, Any]):
        request_id = result.get('requestId')
        camera_id = result.get('cameraId')
        group_index = result.get('groupIndex')
        
        # 1. 从 Redis 获取检测数据（包含群组总数）
        detection_data = self._get_detection_from_redis(request_id)
        if not detection_data:
            logger.warning(f"Detection data not found for {request_id}")
            return
        
        expected_count = len(detection_data.get('trafficGroups', []))
        
        # 2. 聚合该群组的结果
        with self.result_locks[request_id]:
            self.pending_results[request_id].append(result)
            self.expected_groups[request_id] = expected_count
            
            current_count = len(self.pending_results[request_id])
            
            # 3. 如果所有群组结果都收到了，进行聚合
            if current_count >= expected_count:
                all_results = self.pending_results.pop(request_id)
                self.expected_groups.pop(request_id)
                self.result_locks.pop(request_id)
                
                # 4. 计算整体风险
                merged_result = self._merge_all_group_results(
                    detection_data,
                    all_results
                )
                
                # 5. 发布到 WebSocket
                self._publish_to_websocket(camera_id, merged_result)
    
    def _merge_all_group_results(
        self,
        detection_data: Dict[str, Any],
        all_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """聚合所有群组的结果"""
        
        # 收集所有群组的风险等级
        all_group_results = []
        max_risk = "none"
        risk_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        
        for result in all_results:
            group_results = result.get('results', [])
            all_group_results.extend(group_results)
            
            for group_result in group_results:
                risk = group_result.get('riskLevel', 'none')
                if risk_order.get(risk, 0) > risk_order.get(max_risk, 0):
                    max_risk = risk
        
        # 判断是否有危险驾驶
        has_dangerous = max_risk != "none"
        
        # 构建最终结果
        return {
            **detection_data,
            'riskAssessment': {
                'allGroupResults': all_group_results,
                'resultCount': len(all_group_results),
            },
            'hasDangerousDriving': has_dangerous,
            'maxRiskLevel': max_risk,
            'llmLatency': max(r.get('metadata', {}).get('llmLatency', 0) for r in all_results),
            'llmModel': all_results[0].get('metadata', {}).get('llmModel', '') if all_results else '',
        }
```

### 方案 B：保持当前架构，修复逻辑（简单但不完美）

**问题**：ResultAggregator 每次收到一个群组结果就发布一次

**简单修复**：在 Redis 中缓存并更新最大风险

```python
# result_aggregator.py
def handle_assessment_result(self, result: Dict[str, Any]):
    request_id = result.get('requestId')
    camera_id = result.get('cameraId')
    
    # 1. 获取当前群组的风险等级
    current_risk = result.get('results', [{}])[0].get('riskLevel', 'none')
    
    # 2. 从 Redis 获取或初始化风险跟踪
    risk_key = f"risk_tracking:{request_id}"
    existing_risk = self.redis_client.get(risk_key) or "none"
    
    # 3. 更新最大风险
    risk_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    if risk_order.get(current_risk, 0) > risk_order.get(existing_risk, 0):
        max_risk = current_risk
        self.redis_client.setex(risk_key, 300, max_risk)
    else:
        max_risk = existing_risk
    
    # 4. 使用更新后的 max_risk
    merged_result = {
        ...,
        'hasDangerousDriving': max_risk != 'none',
        'maxRiskLevel': max_risk,
    }
```

**缺点**：
- 仍然会多次发布到 WebSocket
- 前端会收到多次更新
- 不够优雅

## 推荐方案

**使用方案 A**：
1. LLMScheduler 只返回单个群组的结果
2. ResultAggregator 等待所有群组结果，聚合后一次性发布
3. 更符合微服务的职责分离原则
4. 数据更准确，前端只收到一次完整结果

## 影响评估

### 当前问题的影响

1. **前端收到错误的风险等级**
   - 例如：群组 0 的 "low" 被发布为整体的 "maxRiskLevel"
   - 后续群组 1 的 "medium" 又被发布，覆盖前面的

2. **WebSocket 消息混乱**
   - 同一次检测发送多次消息
   - 前端需要自己判断哪次是最终结果

3. **日志混淆**
   - 每个群组都打印 "hasDangerous=true, maxRisk=xxx"
   - 无法准确反映整体情况

### 修复后的改进

1. **准确的风险评估**
   - 真正的最高风险等级
   - 正确的危险驾驶判断

2. **清晰的数据流**
   - 每次检测只发送一次 WebSocket 消息
   - 包含所有群组的完整评估结果

3. **更好的调试体验**
   - 日志清晰反映聚合过程
   - 易于追踪问题

## 下一步行动

1. **立即修复**：实现方案 A
2. **添加测试**：验证多群组场景
3. **更新文档**：说明新的数据结构
4. **部署监控**：确保修复生效

---

**发现时间**：2025-10-21  
**严重程度**：高（影响风险评估准确性）  
**推荐方案**：方案 A（聚合后发布）
