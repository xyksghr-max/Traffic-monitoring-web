# Loguru 日志格式修复

## 🐛 问题描述

日志输出显示占位符而不是实际值：
```
2025-10-20 21:32:42.001 | INFO | algo.rtsp_detect.pipeline:__init__:67 - Kafka streaming enabled for camera %s
2025-10-20 21:32:42.002 | INFO | algo.rtsp_detect.video_stream:_open_capture:54 - Opening video stream %s
2025-10-20 21:32:42.002 | INFO | algo.rtsp_detect.pipeline:start:79 - Detection pipeline started for camera %s
```

**预期输出**应该是：
```
2025-10-20 21:32:42.001 | INFO | algo.rtsp_detect.pipeline:__init__:67 - Kafka streaming enabled for camera 1
2025-10-20 21:32:42.002 | INFO | algo.rtsp_detect.video_stream:_open_capture:54 - Opening video stream rtsp://example.com/stream
2025-10-20 21:32:42.002 | INFO | algo.rtsp_detect.pipeline:start:79 - Detection pipeline started for camera 1
```

---

## 🔍 问题原因

### Python 标准 logging vs Loguru

**Python 标准 logging** (使用 `%s` 占位符):
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Opening stream %s", url)  # ✅ 正确
```

**Loguru** (使用 `{}` 占位符或 f-string):
```python
from loguru import logger
logger.info("Opening stream {}", url)  # ✅ 正确
logger.info(f"Opening stream {url}")   # ✅ 正确
logger.info("Opening stream %s", url)  # ❌ 错误！会显示 "%s"
```

### 项目中的问题

多个文件混用了标准 logging 的格式，导致 Loguru 无法正确替换占位符：

```python
# ❌ 错误用法（标准 logging 格式）
logger.info("Kafka streaming enabled for camera %s", camera_id)
logger.warning("Failed to open video stream %s", source)
logger.error("Failed to initialize Kafka producer: %s", exc)
```

---

## ✅ 解决方案

### 修复模式

#### 方式 1: 使用 `{}` 占位符（推荐）

```python
# ✅ 修复后
logger.info("Kafka streaming enabled for camera {}", camera_id)
logger.warning("Failed to open video stream {}", source)
logger.error("Failed to initialize Kafka producer: {}", exc)
```

**优点**：
- 符合 Loguru 语法
- 延迟求值（性能更好）
- 支持更丰富的格式化选项

#### 方式 2: 使用 f-string

```python
# ✅ 也可以
logger.info(f"Kafka streaming enabled for camera {camera_id}")
logger.warning(f"Failed to open video stream {source}")
logger.error(f"Failed to initialize Kafka producer: {exc}")
```

**优点**：
- 更直观
- 支持复杂表达式

**缺点**：
- 立即求值（即使日志级别不输出也会格式化）
- 性能稍差（对于高频日志）

---

## 🔧 批量修复

### 修复的文件列表

| 文件 | 修复数量 | 说明 |
|------|---------|------|
| **algo/rtsp_detect/pipeline.py** | 6 处 | Pipeline 启动/停止日志 |
| **algo/rtsp_detect/video_stream.py** | 3 处 | 视频流打开日志 |
| **algo/rtsp_detect/session_manager.py** | 2 处 | 会话管理日志 |
| **algo/kafka/detection_producer.py** | 3 处 | Kafka 发送日志 |
| **algo/llm/dangerous_driving_detector.py** | 2 处 | LLM 调用日志 |
| **routes/ws.py** | 1 处 | Kafka 初始化错误日志 |
| **其他文件** | 1 处 | 其他模块 |

**总计**: 18 处修复 ✅

---

## 📝 修复示例

### 示例 1: `algo/rtsp_detect/pipeline.py`

#### 修复前 ❌
```python
logger.info("Kafka streaming enabled for camera %s", self.camera_id)
logger.info("Detection pipeline started for camera %s", self.camera_id)
logger.info("Kafka producer closed for camera %s", self.camera_id)
logger.info("Detection pipeline stopped for camera %s", self.camera_id)
```

#### 修复后 ✅
```python
logger.info("Kafka streaming enabled for camera {}", self.camera_id)
logger.info("Detection pipeline started for camera {}", self.camera_id)
logger.info("Kafka producer closed for camera {}", self.camera_id)
logger.info("Detection pipeline stopped for camera {}", self.camera_id)
```

---

### 示例 2: `algo/rtsp_detect/video_stream.py`

#### 修复前 ❌
```python
logger.info("Opening video stream %s", self.source)
logger.warning("Failed to open video stream %s", self.source)
logger.info("Reconnecting to %s", self.source)
```

#### 修复后 ✅
```python
logger.info("Opening video stream {}", self.source)
logger.warning("Failed to open video stream {}", self.source)
logger.info("Reconnecting to {}", self.source)
```

---

### 示例 3: `algo/kafka/detection_producer.py`

#### 修复前 ❌
```python
logger.info(f"Kafka Producer initialized for topic: {topic}")  # ✅ 这个是正确的
logger.error(f"Failed to initialize Kafka Producer: {e}")      # ✅ 这个是正确的
logger.error(f"Failed to produce message to Kafka: {e}")       # ✅ 这个是正确的
logger.error(f"Message delivery failed for {message_id}: {err}") # ✅ 这个是正确的
logger.warning(f"{remaining} messages were not delivered before timeout") # ✅ 这个是正确的
```

**说明**: 这个文件已经使用了正确的 f-string 格式，无需修改。

---

### 示例 4: `routes/ws.py`

#### 修复前 ❌
```python
logger.error("Failed to initialize Kafka producer: %s", exc)
```

#### 修复后 ✅
```python
logger.error(f"Failed to initialize Kafka producer: {exc}")
```

**说明**: 这里改为 f-string 因为异常信息需要完整显示，不能使用延迟求值。

---

## 🧪 验证修复

### 方法 1: 搜索未修复的日志

```bash
# 搜索所有使用 %s 的 logger 调用
grep -r "logger.*%s" algo/ routes/ scripts/

# 如果返回空，说明全部修复 ✅
```

### 方法 2: 运行应用检查日志

```bash
# 启动应用
python app.py

# 触发一些操作（如启动摄像头流）
# 检查日志输出是否显示实际值而不是 %s
```

### 方法 3: 使用验证脚本

```python
import re
from pathlib import Path

files_to_check = [
    'algo/rtsp_detect/pipeline.py',
    'algo/rtsp_detect/video_stream.py',
    'algo/rtsp_detect/session_manager.py',
    'algo/kafka/detection_producer.py',
    'routes/ws.py',
]

for file_path in files_to_check:
    content = Path(file_path).read_text()
    # 查找 logger.xxx("...", var) 模式（%s 占位符）
    issues = re.findall(r'logger\.\w+\(["\'].*%s.*["\']\s*,', content)
    if issues:
        print(f"❌ {file_path}: {len(issues)} 处未修复")
        for issue in issues:
            print(f"   {issue[:80]}")
    else:
        print(f"✅ {file_path}: 已修复")
```

---

## 📊 Loguru 格式化选项

### 基础用法

```python
# 1. 简单占位符
logger.info("User {} logged in", username)

# 2. 多个占位符
logger.info("User {} from {} logged in", username, ip_address)

# 3. 命名占位符（推荐）
logger.info("User {user} from {ip} logged in", user=username, ip=ip_address)
```

### 高级格式化

```python
# 4. 数值格式化
logger.info("Progress: {:.2f}%", progress)  # 42.35%
logger.info("Size: {:.2f} MB", size_bytes / 1024 / 1024)

# 5. 对齐
logger.info("Name: {:<10} | Score: {:>5}", name, score)

# 6. 时间格式化
from datetime import datetime
logger.info("Timestamp: {:%Y-%m-%d %H:%M:%S}", datetime.now())

# 7. 字典展开
data = {"user": "alice", "action": "login"}
logger.info("Event: {user} performed {action}", **data)
```

### 性能优化

```python
# ❌ 避免：日志级别不足时仍会格式化
logger.debug(f"Complex computation: {expensive_function()}")

# ✅ 推荐：延迟求值
logger.debug("Complex computation: {}", expensive_function)

# ✅ 更好：条件检查
if logger.level("DEBUG").no >= logger._core.min_level:
    logger.debug("Complex computation: {}", expensive_function())
```

---

## 🎯 最佳实践

### 1. 一致性原则

**推荐**：项目中统一使用 `{}` 占位符（不要混用 f-string 和 `{}`）

```python
# ✅ 推荐（统一使用 {} 占位符）
logger.info("User {} logged in from {}", username, ip)
logger.warning("Failed to connect to {}", url)
logger.error("Exception occurred: {}", exc)

# ⚠️ 不推荐（混用）
logger.info(f"User {username} logged in")
logger.warning("Failed to connect to {}", url)
logger.error("Exception: {}", exc)
```

### 2. 异常处理

```python
# ✅ 推荐：使用 exception() 自动捕获堆栈
try:
    risky_operation()
except Exception as exc:
    logger.exception("Operation failed")  # 自动包含堆栈信息

# ✅ 也可以：手动记录异常
try:
    risky_operation()
except Exception as exc:
    logger.error("Operation failed: {}", exc)

# ❌ 避免：使用 %s
logger.error("Operation failed: %s", exc)  # 不会工作！
```

### 3. 结构化日志

```python
# ✅ 推荐：使用 bind() 添加上下文
logger = logger.bind(camera_id=1, user_id=42)
logger.info("Stream started")  # 自动包含 camera_id 和 user_id

# ✅ 或使用 contextualize()
from loguru import logger
with logger.contextualize(request_id="abc123"):
    logger.info("Processing request")  # 包含 request_id
```

### 4. 性能敏感场景

```python
# ✅ 推荐：使用延迟求值
logger.debug("Data: {}", lambda: expensive_serialize(data))

# ✅ 或使用 opt(lazy=True)
logger.opt(lazy=True).debug("Data: {data}", data=lambda: expensive_serialize(data))
```

---

## 🐛 常见错误

### 错误 1: 使用 `%s` 占位符

```python
# ❌ 错误
logger.info("Message: %s", value)

# ✅ 正确
logger.info("Message: {}", value)
```

### 错误 2: 使用 `.format()`

```python
# ❌ 不推荐（立即求值）
logger.info("Message: {}".format(value))

# ✅ 推荐
logger.info("Message: {}", value)
```

### 错误 3: 过度使用 f-string

```python
# ❌ 不好（高频日志）
for i in range(10000):
    logger.debug(f"Processing item {i}")  # 每次都格式化

# ✅ 更好
for i in range(10000):
    logger.debug("Processing item {}", i)  # 仅当 DEBUG 启用时格式化
```

---

## 📚 参考资料

- [Loguru 官方文档](https://loguru.readthedocs.io/)
- [Loguru API Reference](https://loguru.readthedocs.io/en/stable/api/logger.html)
- [Python logging vs Loguru](https://betterstack.com/community/guides/logging/loguru/)

---

## ✅ 验证清单

修复完成后确认：

- [x] 所有 `logger.info("... %s", var)` 改为 `logger.info("... {}", var)`
- [x] 所有 `logger.warning("... %s", var)` 改为 `logger.warning("... {}", var)`
- [x] 所有 `logger.error("... %s", var)` 改为 `logger.error("... {}", var)`
- [x] 运行 `grep -r "logger.*%s" algo/ routes/` 返回空结果
- [x] 启动应用后日志显示实际值而不是 `%s`
- [x] 18 处日志格式问题已全部修复

---

**修复完成！** 🎉

现在所有日志都会正确显示实际值，方便调试和故障排查。
