# 问题解决方案：前端风险显示为 "none"

## 问题描述

用户反馈：有时候运行后，前端显示的风险只有 none，数据没有发送给大模型

## 根本原因分析

经过代码分析，发现前端显示 "none" 风险的原因可能有以下几种：

### 1. API Key 未设置 ❌ （最常见）

**症状：** 风险始终显示 "none"

**原因：** `DASHSCOPE_API_KEY` 环境变量未设置，导致 LLM 分析功能被禁用

**日志特征：**
```
🔴 DASHSCOPE_API_KEY not set, LLM analysis DISABLED. 
Set DASHSCOPE_API_KEY environment variable to enable risk detection.
```

**解决方法：**
```bash
# 设置环境变量
export DASHSCOPE_API_KEY="你的API密钥"

# 或在 .env 文件中设置
DASHSCOPE_API_KEY=你的API密钥
```

### 2. LLM 在配置中被禁用 ❌

**症状：** 风险始终显示 "none"

**原因：** `model_config.yaml` 中 `llm.enabled` 设置为 `false`

**日志特征：**
```
🔴 Dangerous driving analysis DISABLED via configuration (llm.enabled=false)
```

**解决方法：**
编辑 `model_config.yaml`：
```yaml
llm:
  enabled: true  # 改为 true
```

### 3. LLM 冷却期 ⏱️ （正常行为）

**症状：** 风险间歇性显示 "none"

**原因：** 
- LLM 调用很昂贵，系统设置了 3 秒冷却时间
- 在冷却期间，系统使用缓存的告警结果
- 这是正常的设计行为

**日志特征：**
```
LLM analysis skipped: cooldown active (1.2s / 3.0s)
Camera 1: Using 2 cached alerts (LLM cooldown), highest_risk=high
```

**说明：**
- 这是**正常现象**！
- `RiskAlertManager` 会在 3 秒内保持告警显示
- 不需要每帧都调用 LLM

**如果需要调整冷却时间：**
```yaml
llm:
  cooldown_seconds: 2.0  # 从 3.0 改为 2.0
```

### 4. 无群组图像 🖼️

**症状：** 交通稀疏时显示 "none"

**原因：**
- LLM 需要分析交通群组的裁剪图像
- 当交通稀疏时，无法形成群组
- 无群组则无需分析风险

**日志特征：**
```
LLM analysis skipped: no group images (detections=2, groups=1)
```

**说明：** 这是预期行为，交通稀疏时确实没有风险可检测

### 5. 检测目标不足 📊

**症状：** 低流量时显示 "none"

**原因：** LLM 只在以下情况触发：
- 检测到 2 个或以上目标，或
- 至少存在 1 个交通群组

**日志特征：**
```
LLM analysis skipped: insufficient detections (detections=1, groups=0, group_images=1)
```

**说明：** 正常行为 - 系统在流量低时节省 API 调用

## 已实施的解决方案

### 1. 增强日志功能 ✅

**启动时日志：**
- ✅ 成功初始化时显示模型和冷却时间
- 🔴 API Key 缺失时显示明确错误信息
- 🔴 LLM 被禁用时显示配置状态

**运行时日志：**
- 显示为什么跳过 LLM 分析（禁用、冷却、无图像、检测不足）
- 显示何时触发 LLM 分析（附带检测/群组数量）
- 显示 LLM 结果和风险等级
- 显示何时使用缓存告警

### 2. 修复 Bug ✅

修复了初始化代码中的 bug：
```python
# 之前（错误）
self.client = OpenAI(...)

# 现在（正确）
self._client = OpenAI(...)
```

### 3. 完善文档 ✅

创建了三份文档：

1. **完整故障排查指南** - `docs/LLM_RISK_DETECTION_GUIDE.md`
   - LLM 风险检测工作原理
   - 常见问题原因和解决方案
   - 日志理解和调试
   - 配置参考
   - FAQ 和最佳实践

2. **快速诊断指南** - `docs/QUICK_START_LLM_DEBUG.md`
   - 快速诊断常见问题
   - 配置检查清单
   - 日志位置

3. **README 更新**
   - 添加故障排查章节
   - 链接到详细文档

## 如何使用

### 快速诊断步骤

1. **检查 API Key**
```bash
echo $DASHSCOPE_API_KEY
# 应该输出你的 API 密钥
```

2. **查看启动日志**
```bash
# 启动应用
python app.py

# 查找这些消息：
# ✅ Dangerous driving analyzer initialized: model=qwen-vl-plus, cooldown=3.0s
# 或
# 🔴 DASHSCOPE_API_KEY not set, LLM analysis DISABLED
```

3. **检查配置文件**
```bash
cat model_config.yaml | grep -A5 "llm:"
# 确保 enabled: true
```

4. **监控运行日志**
```bash
# 查看检测情况
grep "detections=" logs/app.log | tail -20

# 查看 LLM 调用
grep "LLM" logs/app.log | tail -20
```

### 日志示例

**正常运行（LLM 分析成功）：**
```
2025-10-20 10:00:00 | SUCCESS  | ✅ Dangerous driving analyzer initialized: model=qwen-vl-plus, cooldown=3.0s
2025-10-20 10:00:05 | DEBUG    | Camera 1: frame analysis - detections=5, groups=2, group_images=2
2025-10-20 10:00:05 | DEBUG    | LLM analysis triggered: 5 detections (>=2), 2 groups, 2 group images
2025-10-20 10:00:08 | INFO     | Camera 1: LLM detected 2 alerts, max_risk=high
```

**正常运行（使用缓存）：**
```
2025-10-20 10:00:10 | DEBUG    | LLM analysis skipped: cooldown active (2.1s / 3.0s)
2025-10-20 10:00:10 | DEBUG    | Camera 1: Using 2 cached alerts (LLM cooldown), highest_risk=high
```

**配置错误（API Key 缺失）：**
```
2025-10-20 10:00:00 | WARNING  | 🔴 DASHSCOPE_API_KEY not set, LLM analysis DISABLED. Set DASHSCOPE_API_KEY environment variable to enable risk detection.
```

## PowerShell 启动脚本

项目已包含 PowerShell 启动脚本：

```powershell
# 启动所有流式处理服务
.\scripts\start_all_streaming.ps1

# 停止所有服务
.\scripts\stop_all_streaming.ps1
```

该脚本会：
1. 检查 Docker 环境
2. 启动基础设施（Kafka, Redis, Prometheus, Grafana）
3. 初始化 Kafka Topics
4. 启动流式处理服务
5. 启动 Flask 应用

## 性能说明

### API 成本控制

- 每次 LLM 调用都有成本（DashScope API）
- 冷却机制防止过度使用 API
- 目标：每个摄像头每分钟约 20-30 次调用

### 延迟处理

- LLM 调用需要 2-10 秒
- 在此期间系统使用缓存告警
- 前端保持响应

### RiskAlertManager 状态管理

- 告警显示窗口：3 秒
- 相同风险类型：保持原有倒计时
- 不同风险类型：重置倒计时
- 多个风险：合并为一个告警

## 常见问题

### Q: 为什么风险突然从 "high" 变成 "none"？

**A:** 可能原因：
1. 3 秒显示窗口已过期
2. 新的 LLM 分析返回无风险
3. 危险情况已解除

### Q: 可以让 LLM 分析每一帧吗？

**A:** 不推荐：
- API 成本太高
- 可能触发速率限制
- 没有必要（3 秒显示窗口提供连续性）

### Q: 为什么有交通时风险不立即显示？

**A:** LLM 需要：
1. 检测到目标
2. 形成群组
3. 生成群组图像
4. 冷却期结束（如果最近调用过）

通常需要 1-2 帧（2-4 秒）

## 文档链接

- 📖 [完整故障排查指南](docs/LLM_RISK_DETECTION_GUIDE.md)
- 🚀 [快速诊断指南](docs/QUICK_START_LLM_DEBUG.md)
- 📚 [Kafka 集成指南](KAFKA_INTEGRATION_GUIDE.md)
- 🛠️ [部署指南](DEPLOYMENT_GUIDE.md)

## 总结

通过添加详细的日志记录和完善的文档，现在可以轻松诊断和解决 "前端显示风险为 none" 的问题。主要改进包括：

1. ✅ **清晰的启动日志** - 立即知道 LLM 是否正常初始化
2. ✅ **详细的运行日志** - 理解为什么跳过或触发 LLM 分析
3. ✅ **完整的文档** - 涵盖所有常见问题和解决方案
4. ✅ **Bug 修复** - 修正了客户端初始化错误

现在用户可以通过查看日志快速定位问题，并参考文档找到解决方案。
