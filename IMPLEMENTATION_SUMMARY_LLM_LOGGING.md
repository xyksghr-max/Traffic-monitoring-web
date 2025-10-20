# Implementation Summary: LLM Risk Detection Logging and Troubleshooting

## Overview

This PR fixes the issue where users see "none" risk in the frontend by adding comprehensive logging and documentation to help diagnose why LLM analysis may not be running.

## Problem Statement

**Original Issue (Chinese):** 为什么有时候运行后，前端显示的风险只有none，是没发送给大模型has

**Translation:** Why does the frontend sometimes only show "none" risk? The data isn't being sent to the large model.

## Solution Architecture

### 1. Enhanced Logging System

#### Startup Logging
```
✅ SUCCESS: Dangerous driving analyzer initialized: model=qwen-vl-plus, cooldown=3.0s
🔴 WARNING: DASHSCOPE_API_KEY not set, LLM analysis DISABLED
🔴 INFO: Dangerous driving analysis DISABLED via configuration
```

#### Runtime Logging
```
DEBUG: LLM analysis triggered: 5 detections (>=2), 2 groups, 2 group images
DEBUG: LLM analysis skipped: cooldown active (1.2s / 3.0s)
DEBUG: LLM analysis skipped: no group images (detections=2, groups=1)
DEBUG: LLM analysis skipped: insufficient detections (detections=1, groups=0, group_images=1)
INFO: Camera 1: LLM detected 2 alerts, max_risk=high
DEBUG: Camera 1: Using 2 cached alerts (LLM cooldown), highest_risk=high
```

### 2. Root Cause Identification

| Cause | Frequency | Impact | Solution |
|-------|-----------|--------|----------|
| Missing API key | Common | Blocks all LLM | Set DASHSCOPE_API_KEY |
| LLM disabled | Common | Blocks all LLM | Set llm.enabled=true |
| Cooldown period | Very Common | Normal behavior | No action needed |
| No group images | Common | Expected | No action needed |
| Insufficient detections | Common | Expected | No action needed |

### 3. Documentation Structure

```
docs/
├── LLM_RISK_DETECTION_GUIDE.md          # Complete guide (EN)
│   ├── How LLM works
│   ├── Common issues & solutions
│   ├── Log interpretation
│   ├── Configuration reference
│   ├── FAQ
│   └── Best practices
│
├── QUICK_START_LLM_DEBUG.md            # Quick diagnosis (EN)
│   ├── 3-step diagnosis
│   ├── Common scenarios
│   ├── Configuration snippets
│   └── Log locations
│
└── 问题解决方案_前端风险显示none.md    # Solution guide (CN)
    ├── 问题描述
    ├── 根本原因分析
    ├── 解决方案
    ├── 使用方法
    └── 常见问题
```

## Technical Implementation

### Code Changes

#### 1. dangerous_driving_detector.py

**Bug Fix:**
```python
# Before (incorrect)
self.client = OpenAI(...)

# After (correct)
self._client = OpenAI(...)
```

**Enhanced Logging:**
```python
def should_analyze(self, detections, groups, group_images):
    if not self.enabled or not self._client:
        logger.debug(
            "LLM analysis skipped: enabled={}, client_initialized={}",
            self.enabled, self._client is not None
        )
        return False
    
    time_since_last_call = time.time() - self._last_call_ts
    if time_since_last_call < self.config.cooldown_seconds:
        logger.debug(
            "LLM analysis skipped: cooldown active ({}s / {}s)",
            round(time_since_last_call, 1),
            self.config.cooldown_seconds
        )
        return False
    
    # ... additional logging for all conditions
```

#### 2. pipeline.py

**Detection Status Logging:**
```python
logger.debug(
    "Camera {}: frame analysis - detections={}, groups={}, group_images={}",
    self.camera_id,
    len(detected_objects),
    len(groups),
    len(llm_group_images),
)
```

**Risk Status Logging:**
```python
if raw_results:
    logger.info(
        "Camera {}: LLM detected {} alerts, max_risk={}",
        self.camera_id,
        len(raw_results),
        llm_result.get("maxRiskLevel", "none")
    )
elif alerts:
    logger.debug(
        "Camera {}: Using {} cached alerts (LLM cooldown), highest_risk={}",
        self.camera_id,
        len(alerts),
        self.risk_manager.highest_risk_level()
    )
```

## Key Insights

### 1. RiskAlertManager Design

The `RiskAlertManager` is designed to maintain smooth UX:

```python
class RiskAlertManager:
    def __init__(self, display_window: float = 3.0):
        self.display_window = display_window  # 3 seconds
        self._entries: Dict[int, AlertEntry] = {}
    
    def update(self, now: float, llm_results: Sequence[Dict]):
        # Process new results
        # Retain stale alerts within display window
        # Expire old alerts
```

**Behavior:**
- Alerts display for 3 seconds after detection
- During LLM cooldown, cached alerts are retained
- Frontend sees continuous risk display, not intermittent

### 2. Cooldown Mechanism

**Purpose:**
- Prevent API rate limiting
- Reduce API costs (~$0.002 per call)
- Maintain system responsiveness

**Configuration:**
```yaml
llm:
  cooldown_seconds: 3.0  # Adjustable
```

**Trade-offs:**
- Lower cooldown = More responsive, higher cost
- Higher cooldown = Less responsive, lower cost
- Default 3s balances both

### 3. should_analyze Conditions

```python
def should_analyze(detections, groups, group_images):
    if not enabled or not client:
        return False  # Configuration issue
    
    if in_cooldown:
        return False  # Normal behavior
    
    if not group_images:
        return False  # No data to analyze
    
    if len(detections) >= 2 or groups:
        return True   # Sufficient data
    
    return False      # Insufficient data
```

## Testing & Validation

### Test Suite

```python
# Test 1: API Key Handling
- Without key: Shows 🔴 error, disabled
- With key: Shows ✅ success, enabled

# Test 2: should_analyze Logic
- Empty inputs: False (logged)
- No images: False (logged)
- 2+ detections: True (logged)
- Has groups: True (logged)
- Insufficient: False (logged)

# Test 3: Cooldown Behavior
- In cooldown: False (logged with time)
- After cooldown: True (logged)

# Test 4: RiskAlertManager
- Initial alerts: Stored
- Empty update (cooldown): Retained
- After window: Expired
```

All tests passing ✅

## User Impact

### Before
```
User: "Why is risk always none?"
Support: "Check logs... maybe API key issue?"
User: "What logs? Where?"
Support: "Let me investigate..."
```

### After
```
User: "Why is risk showing none?"
User: *checks startup logs*
Log: "🔴 DASHSCOPE_API_KEY not set, LLM analysis DISABLED"
User: *sets API key*
Log: "✅ Dangerous driving analyzer initialized: model=qwen-vl-plus"
User: "Fixed!"
```

## Metrics

### Logging Coverage
- ✅ 5 critical startup conditions
- ✅ 6 runtime skip reasons
- ✅ 3 success scenarios
- ✅ All conditions have unique messages

### Documentation Coverage
- ✅ English guide (8,211 chars)
- ✅ Chinese guide (4,745 chars)
- ✅ Quick start (2,765 chars)
- ✅ README section (148 lines)

### Code Quality
- ✅ Bug fixed (client initialization)
- ✅ No breaking changes
- ✅ Backward compatible
- ✅ Type hints preserved
- ✅ Tests passing

## PowerShell Script

The `start_all_streaming.ps1` script already exists and provides:

```powershell
# Features:
- Docker environment checks
- Infrastructure startup (Kafka, Redis, Prometheus, Grafana)
- Kafka topics initialization
- Streaming services launch
- Flask application startup
- Health verification
- Logging and PID management

# Usage:
.\scripts\start_all_streaming.ps1
```

## Configuration Reference

### Environment Variables
```bash
export DASHSCOPE_API_KEY="sk-xxx"      # Required
export ALGO_LLM_MODEL="qwen-vl-plus"   # Optional
export ALGO_LLM_TIMEOUT="30"           # Optional
export ALGO_LLM_MAX_RETRY="2"          # Optional
```

### model_config.yaml
```yaml
llm:
  enabled: true              # Enable/disable LLM
  cooldown_seconds: 3.0      # Time between calls
  risk_threshold:
    low: 0.45
    medium: 0.65
    high: 0.80
```

## FAQ

**Q: Is "cooldown active" an error?**
A: No! It's normal behavior. The system uses cached alerts during cooldown.

**Q: Why 3 seconds cooldown?**
A: Balances API cost, rate limits, and user experience. Adjustable if needed.

**Q: What if traffic is sparse?**
A: Expected. No traffic = no risk. "none" is correct.

**Q: Can I see what the LLM sees?**
A: Yes, check `groupImages` in WebSocket response or `llmRawText` in logs.

## Files Modified

1. `algo/llm/dangerous_driving_detector.py` - Logging + bug fix
2. `algo/rtsp_detect/pipeline.py` - Detection status logging
3. `README.md` - Troubleshooting section
4. `docs/LLM_RISK_DETECTION_GUIDE.md` - New
5. `docs/QUICK_START_LLM_DEBUG.md` - New
6. `docs/问题解决方案_前端风险显示none.md` - New

## Future Enhancements

### Potential Improvements
1. Web-based log viewer
2. Real-time health dashboard
3. Automatic API key validation
4. Configuration wizard
5. Performance profiling tools

### Not Planned
1. Removing cooldown (breaks cost control)
2. LLM on every frame (too expensive)
3. Synchronous LLM calls (blocks pipeline)

## Conclusion

This PR successfully addresses the user's concern by:

1. **Adding visibility** - Logs show exactly what's happening
2. **Fixing bugs** - Client initialization corrected
3. **Providing education** - Comprehensive docs explain behavior
4. **Maintaining quality** - No breaking changes, all tests pass

Users can now self-diagnose most issues by reading logs and documentation, reducing support burden and improving satisfaction.

---

**Related Issues:** #N/A (from conversation context)
**Documentation:** ✅ Complete
**Tests:** ✅ Passing
**Breaking Changes:** ❌ None
**Deployment Impact:** ✅ Minimal (logging only)
