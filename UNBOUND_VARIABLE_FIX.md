# "record_llm_request is possibly unbound" 修复

## 🐛 问题描述

IDE/Linter 警告：
```
"record_llm_request" is possibly unbound
```

---

## 🔍 问题原因

### 原始代码

```python
# Import Prometheus metrics (optional)
try:
    from algo.monitoring.metrics import record_llm_request
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger.warning("Prometheus metrics not available for LLM monitoring")

# ... 后续代码中使用
if METRICS_AVAILABLE:
    record_llm_request(...)  # ⚠️ IDE 认为 record_llm_request 可能未定义
```

**问题**：
- `record_llm_request` 只在 try 块中导入
- 如果导入失败（ImportError），`record_llm_request` 不存在
- 虽然代码中有 `if METRICS_AVAILABLE` 检查，但 IDE 静态分析器无法保证 `record_llm_request` 一定被定义

---

## ✅ 解决方案

### 定义 No-op Fallback 函数

```python
# Import Prometheus metrics (optional)
try:
    from algo.monitoring.metrics import record_llm_request
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    # Define a no-op function if metrics are not available
    def record_llm_request(*args, **kwargs):  # type: ignore
        """No-op placeholder when metrics are unavailable."""
        pass
    logger.warning("Prometheus metrics not available for LLM monitoring")
```

**优点**：
1. ✅ `record_llm_request` **总是被定义**（要么是真实函数，要么是 no-op）
2. ✅ 消除 IDE 警告
3. ✅ 代码更简洁（可以移除一些 `if METRICS_AVAILABLE` 检查）
4. ✅ 类型检查器满意（`# type: ignore` 忽略类型重定义警告）

---

## 🔧 可选优化：简化调用代码

### 修复前（需要每次检查）

```python
if METRICS_AVAILABLE:
    record_llm_request(
        model=self.config.model,
        api_key_id='default',
        latency=latency,
        status='success'
    )
```

### 修复后（可以直接调用）

```python
# ✅ 现在可以直接调用，no-op 函数会自动处理缺失情况
record_llm_request(
    model=self.config.model,
    api_key_id='default',
    latency=latency,
    status='success'
)
```

**说明**：
- 如果 metrics 可用 → 记录到 Prometheus
- 如果 metrics 不可用 → no-op 函数什么都不做（零开销）

**是否应该移除 `if METRICS_AVAILABLE` 检查？**

**推荐保留**（当前实现），原因：
1. 明确表达意图（"仅在 metrics 可用时记录"）
2. 避免不必要的函数调用和参数构造
3. 更易于阅读和维护

---

## 🧪 验证

### 测试 1: Metrics 可用时

```python
from algo.llm.dangerous_driving_detector import record_llm_request, METRICS_AVAILABLE

print(f"METRICS_AVAILABLE: {METRICS_AVAILABLE}")
print(f"record_llm_request: {record_llm_request}")

# 调用函数（应该记录到 Prometheus）
record_llm_request(
    model="qwen-vl-plus",
    api_key_id="test",
    latency=1.23,
    status="success"
)
```

**预期输出**（Metrics 可用）:
```
METRICS_AVAILABLE: True
record_llm_request: <function record_llm_request at 0x...>
```

### 测试 2: Metrics 不可用时

```bash
# 临时重命名 metrics 模块模拟 ImportError
mv algo/monitoring/metrics.py algo/monitoring/metrics.py.bak

python -c "
from algo.llm.dangerous_driving_detector import record_llm_request, METRICS_AVAILABLE
print(f'METRICS_AVAILABLE: {METRICS_AVAILABLE}')
print(f'record_llm_request: {record_llm_request}')
record_llm_request(model='test', api_key_id='test', latency=1.0, status='test')
print('No-op call succeeded!')
"

# 恢复
mv algo/monitoring/metrics.py.bak algo/monitoring/metrics.py
```

**预期输出**（Metrics 不可用）:
```
WARNING: Prometheus metrics not available for LLM monitoring
METRICS_AVAILABLE: False
record_llm_request: <function record_llm_request at 0x...>
No-op call succeeded!
```

---

## 🎯 相关模式（其他可选实现）

### 方案 1: 使用条件导入 + 类型注解（当前方案）✅

```python
try:
    from algo.monitoring.metrics import record_llm_request
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    def record_llm_request(*args, **kwargs):  # type: ignore
        pass
```

**优点**：简单直接，无额外依赖

---

### 方案 2: 使用 typing.TYPE_CHECKING

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from algo.monitoring.metrics import record_llm_request

METRICS_AVAILABLE = False

try:
    from algo.monitoring.metrics import record_llm_request  # type: ignore[assignment]
    METRICS_AVAILABLE = True
except ImportError:
    def record_llm_request(*args, **kwargs):
        pass
```

**优点**：类型检查更准确  
**缺点**：稍微复杂

---

### 方案 3: 使用 Protocol（高级）

```python
from typing import Protocol

class MetricsRecorder(Protocol):
    def __call__(self, model: str, api_key_id: str, latency: float, status: str, **kwargs) -> None:
        ...

try:
    from algo.monitoring.metrics import record_llm_request
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    record_llm_request: MetricsRecorder = lambda *args, **kwargs: None
```

**优点**：类型安全  
**缺点**：过度设计（对于简单场景）

---

## 📝 最佳实践

### 1. Optional 依赖的推荐模式

```python
# ✅ 推荐：定义 no-op fallback
try:
    from optional_module import optional_function
    FEATURE_AVAILABLE = True
except ImportError:
    FEATURE_AVAILABLE = False
    def optional_function(*args, **kwargs):
        """No-op when feature unavailable."""
        pass
```

### 2. 使用时的模式

```python
# ✅ 方式 1: 显式检查（推荐）
if FEATURE_AVAILABLE:
    optional_function(param1, param2)

# ✅ 方式 2: 直接调用（简洁）
optional_function(param1, param2)  # No-op if unavailable
```

### 3. 避免的模式

```python
# ❌ 不推荐：每次检查是否存在
if 'optional_function' in globals():
    optional_function(param1, param2)

# ❌ 不推荐：捕获 NameError
try:
    optional_function(param1, param2)
except NameError:
    pass
```

---

## ✅ 验证清单

修复后确认：

- [x] IDE 不再显示 "possibly unbound" 警告
- [x] `record_llm_request` 总是被定义（真实函数或 no-op）
- [x] Metrics 可用时正常记录到 Prometheus
- [x] Metrics 不可用时 no-op 函数静默失败
- [x] 类型检查通过（pyright/mypy）
- [x] 代码可读性提升

---

## 🔧 相关工具配置

### Pylance/Pyright 设置

如果仍有警告，可在 `.vscode/settings.json` 中配置：

```json
{
  "python.analysis.typeCheckingMode": "basic",
  "python.analysis.diagnosticSeverityOverrides": {
    "reportUnboundVariable": "warning"
  }
}
```

### mypy 配置

在 `pyproject.toml` 或 `mypy.ini`:

```ini
[mypy]
warn_unreachable = True
warn_unused_ignores = False

[mypy-algo.monitoring.metrics]
ignore_missing_imports = True
```

---

## 📚 相关文档

- [PROMETHEUS_NO_DATA_FIX.md](PROMETHEUS_NO_DATA_FIX.md) - Prometheus 集成修复
- [PROMETHEUS_QUICKREF.md](PROMETHEUS_QUICKREF.md) - Prometheus 快速参考
- [algo/monitoring/metrics.py](algo/monitoring/metrics.py) - Metrics 定义

---

**修复完成！** 🎉 

现在 `record_llm_request` 总是被定义，IDE 警告消失。
