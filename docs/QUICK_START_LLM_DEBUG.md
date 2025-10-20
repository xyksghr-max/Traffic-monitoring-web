# Quick Start: LLM Risk Detection

## Problem: Frontend Shows "None" Risk

If you're seeing "none" risk in the frontend even when there's traffic, follow this guide.

## Quick Diagnosis

### 1. Check if LLM is enabled

**Look for this log on startup:**
```
✅ Dangerous driving analyzer initialized: model=qwen-vl-plus, cooldown=3.0s
```

**If you see this instead:**
```
🔴 DASHSCOPE_API_KEY not set, LLM analysis DISABLED
```
**→ Solution:** Set the API key:
```bash
export DASHSCOPE_API_KEY="your-api-key-here"
```

### 2. Check if traffic is being detected

**Look for these logs:**
```
Camera 1: frame analysis - detections=5, groups=2, group_images=2
```

**If detections/groups/images are all 0:**
- No traffic detected
- Camera might be pointing at empty road
- Check camera feed

### 3. Check if LLM is being called

**Look for these logs:**
```
LLM analysis triggered: 5 detections (>=2), 2 groups, 2 group images
Camera 1: LLM detected 2 alerts, max_risk=high
```

**If you see "skipped" messages:**
```
LLM analysis skipped: cooldown active (1.2s / 3.0s)
Camera 1: Using 2 cached alerts (LLM cooldown), highest_risk=high
```
**→ This is NORMAL!** The system uses cached alerts during cooldown.

## Common Scenarios

### Scenario A: Always "none"
**Cause:** API key not set or LLM disabled
**Solution:** Check logs for 🔴 messages and fix configuration

### Scenario B: Intermittent "none" 
**Cause:** Either cooldown (normal) or sparse traffic (expected)
**Solution:** Check logs to distinguish between the two

### Scenario C: "none" despite heavy traffic
**Cause:** Groups not being formed
**Solution:** Check group analyzer configuration in `model_config.yaml`

## Configuration Files

### model_config.yaml
```yaml
llm:
  enabled: true              # Must be true
  cooldown_seconds: 3.0      # Time between LLM calls
```

### Environment Variables
```bash
export DASHSCOPE_API_KEY="sk-xxxxxxxxxxxx"  # Required!
```

## Log Locations

When running with PowerShell script:
- Flask app: `logs/streaming/flask_app.log`
- Task Generator: `logs/streaming/task_generator.log`
- Scheduler: `logs/streaming/scheduler.log`
- Result Aggregator: `logs/streaming/result_aggregator.log`

When running directly:
- Check console output
- Look for colored emoji indicators (✅ 🔴)

## Full Documentation

See `docs/LLM_RISK_DETECTION_GUIDE.md` for complete troubleshooting guide.

## Quick Test

Run this to verify LLM is working:
```bash
# Check API key is set
echo $DASHSCOPE_API_KEY

# Start the app
python app.py

# Look for this in logs:
# ✅ Dangerous driving analyzer initialized
```

## Still Having Issues?

1. Enable DEBUG logging
2. Check all startup messages
3. Verify API key and quota
4. Review `docs/LLM_RISK_DETECTION_GUIDE.md`
5. Check GitHub issues
