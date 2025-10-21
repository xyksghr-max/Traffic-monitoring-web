# LLM Risk Detection Troubleshooting Guide

## Overview

The Traffic Monitoring system uses a Large Language Model (LLM) to analyze traffic situations and detect dangerous driving behaviors. This guide helps you understand when and why risk detection may show "none" in the frontend.

## How LLM Risk Detection Works

### Process Flow

1. **Video Frame Capture** → Frames captured from RTSP stream
2. **Object Detection** → YOLO detects vehicles, pedestrians, etc.
3. **Group Analysis** → Objects are grouped into traffic clusters
4. **LLM Analysis** → Qwen-VL analyzes group images for risks
5. **Risk Alert Manager** → Maintains alerts with display countdown
6. **Frontend Display** → Shows risk levels and alerts

### Risk Levels

- **none** - No risk detected
- **low** - Minor issues (traffic congestion, close following)
- **medium** - Moderate risks (jaywalking, improper lane changes)
- **high** - Severe risks (collisions, running red lights, dangerous maneuvers)

## Common Reasons for "None" Risk Display

### 1. Missing API Key ❌

**Symptom:** Risk always shows "none"

**Log Message:**
```
🔴 DASHSCOPE_API_KEY not set, LLM analysis DISABLED. Set DASHSCOPE_API_KEY environment variable to enable risk detection.
```

**Solution:**
```bash
export DASHSCOPE_API_KEY="your-api-key-here"
```

### 2. LLM Disabled in Configuration ❌

**Symptom:** Risk always shows "none"

**Log Message:**
```
🔴 Dangerous driving analysis DISABLED via configuration (llm.enabled=false)
```

**Solution:** Edit `model_config.yaml`:
```yaml
llm:
  enabled: true  # Change from false to true
```

### 3. Cooldown Period ⏱️

**Symptom:** Risk shows "none" intermittently

**Log Message:**
```
LLM analysis skipped: cooldown active (1.2s / 3.0s)
```

**Explanation:** 
- LLM calls are expensive and rate-limited
- Default cooldown: 3 seconds between LLM calls
- During cooldown, the system uses **cached alerts** from previous analysis

**Solution:** This is normal behavior! The `RiskAlertManager` maintains alerts for 3 seconds even during cooldown.

**To adjust cooldown:**
```yaml
llm:
  cooldown_seconds: 2.0  # Reduce from 3.0 to 2.0
```

### 4. No Group Images 🖼️

**Symptom:** Risk shows "none" when traffic is sparse

**Log Message:**
```
LLM analysis skipped: no group images (detections=1, groups=0)
```

**Explanation:**
- LLM requires cropped images of traffic groups
- Groups are only created when multiple objects are close together
- If traffic is sparse, no groups are formed

**Solution:** This is expected - there's no risk to detect when traffic is sparse!

### 5. Insufficient Detections 📊

**Symptom:** Risk shows "none" with low traffic volume

**Log Message:**
```
LLM analysis skipped: insufficient detections (detections=1, groups=0, group_images=1)
```

**Explanation:** LLM is only triggered when:
- 2 or more objects are detected, OR
- At least 1 traffic group exists

**Solution:** Normal behavior - system conserves API calls when traffic is light.

## Understanding the Logs

### Successful LLM Analysis ✅

```
2025-10-20 10:00:00 | SUCCESS  | ✅ Dangerous driving analyzer initialized: model=qwen-vl-plus, cooldown=3.0s
2025-10-20 10:00:05 | DEBUG    | Camera 1: frame analysis - detections=5, groups=2, group_images=2
2025-10-20 10:00:05 | DEBUG    | LLM analysis triggered: 5 detections (>=2), 2 groups, 2 group images
2025-10-20 10:00:08 | INFO     | Camera 1: LLM detected 2 alerts, max_risk=high
```

### Using Cached Alerts (Normal) ✅

```
2025-10-20 10:00:10 | DEBUG    | LLM analysis skipped: cooldown active (2.1s / 3.0s)
2025-10-20 10:00:10 | DEBUG    | Camera 1: Using 2 cached alerts (LLM cooldown), highest_risk=high
```

### No Risk to Detect (Normal) ℹ️

```
2025-10-20 10:00:15 | DEBUG    | Camera 1: frame analysis - detections=1, groups=0, group_images=0
2025-10-20 10:00:15 | DEBUG    | LLM analysis skipped: no group images (detections=1, groups=0)
```

## Configuration Reference

### model_config.yaml

```yaml
llm:
  enabled: true              # Enable/disable LLM analysis
  cooldown_seconds: 3.0      # Seconds between LLM calls
  risk_threshold:
    low: 0.45                # Confidence threshold for low risk
    medium: 0.65             # Confidence threshold for medium risk
    high: 0.80               # Confidence threshold for high risk
```

### Environment Variables

```bash
# Required for LLM to work
export DASHSCOPE_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Optional: Override default LLM model
export ALGO_LLM_MODEL="qwen-vl-plus"

# Optional: Override default timeout
export ALGO_LLM_TIMEOUT="30"

# Optional: Override max retries
export ALGO_LLM_MAX_RETRY="2"
```

## Risk Alert Manager

The `RiskAlertManager` maintains state to ensure smooth user experience:

### Display Window (3 seconds)
- Alerts are displayed for 3 seconds after detection
- New detections refresh the timer
- During LLM cooldown, cached alerts are used
- Alerts expire after display window

### Continuation Logic
- Same risk type → Keeps original countdown
- Different risk type → Resets countdown
- Multiple risks → Merged into one alert

## Performance Considerations

### API Costs
- Each LLM call costs money (DashScope API)
- Cooldown prevents excessive API usage
- Target: ~20-30 calls per minute per camera

### Latency
- LLM calls take 2-10 seconds
- During this time, system uses cached alerts
- Frontend remains responsive

## Debugging Steps

### Step 1: Check API Key
```bash
echo $DASHSCOPE_API_KEY
# Should output your API key
```

### Step 2: Check Configuration
```bash
cat model_config.yaml | grep -A5 "llm:"
# Should show enabled: true
```

### Step 3: Check Logs
Look for these key messages:
- ✅ Analyzer initialized successfully
- 🔴 API key missing or LLM disabled
- LLM analysis triggered/skipped messages

### Step 4: Monitor Detections
```bash
# Check if objects are being detected
grep "detections=" logs/app.log | tail -20

# Check if groups are being formed
grep "groups=" logs/app.log | tail -20
```

### Step 5: Verify LLM Responses
```bash
# Check for LLM results
grep "LLM detected" logs/app.log | tail -20

# Check for errors
grep "LLM.*error\|failed" logs/app.log | tail -20
```

## FAQ

### Q: Why does risk suddenly change from "high" to "none"?

**A:** This happens when:
1. The 3-second display window expires
2. New LLM analysis returns no risks
3. The dangerous situation has resolved

### Q: Can I make LLM analyze every frame?

**A:** Not recommended:
- Too expensive (API costs)
- May hit rate limits
- Not necessary (3-second display window provides continuity)

### Q: Why doesn't risk show immediately when traffic appears?

**A:** LLM needs:
1. Objects to be detected
2. Groups to be formed
3. Group images to be generated
4. Cooldown period to pass (if recently called)

This typically takes 1-2 frames (2-4 seconds).

### Q: How can I see what the LLM actually sees?

**A:** The `groupImages` field in the WebSocket response contains the cropped images sent to the LLM. You can:
1. Enable debug logging
2. Check the `llmRawText` field for LLM's raw response
3. Review `groupImages` array in browser DevTools

## Best Practices

1. **Set API Key Properly**
   - Use environment variables
   - Don't commit keys to git

2. **Monitor Logs**
   - Check startup logs for initialization
   - Watch for error messages
   - Use log levels appropriately

3. **Tune Configuration**
   - Adjust cooldown based on your needs
   - Balance cost vs. responsiveness
   - Test with real traffic scenarios

4. **Handle Edge Cases**
   - Expect "none" during sparse traffic
   - Cached alerts are normal during cooldown
   - Display window ensures smooth UX

## Related Files

- `algo/llm/dangerous_driving_detector.py` - LLM integration
- `algo/rtsp_detect/pipeline.py` - Detection pipeline
- `algo/rtsp_detect/risk_alert_manager.py` - Alert state management
- `model_config.yaml` - Configuration
- `config.py` - Environment settings

## Support

If you continue to see "none" risk despite proper configuration:

1. Enable DEBUG logging
2. Check all log messages
3. Verify API key and quota
4. Test with known risky scenarios
5. Review grouping configuration

For more help, check the project documentation or open an issue on GitHub.
