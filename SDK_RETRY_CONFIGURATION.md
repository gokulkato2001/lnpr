# SDK Retry Configuration - Connection Timeout Resolution

## Problem

The Plate Recognizer SDK at `http://31.97.202.17:8080/v1/plate-reader/` was timing out with:
```
[ERROR] Plate Recognizer request failed: HTTPConnectionPool(host='31.97.202.17', port=8080): 
Max retries exceeded with url: /v1/plate-reader/ (Caused by ConnectTimeoutError)
```

## Solution Implemented

Added **infinite retry mechanism** with exponential backoff to handle:
- Connection timeouts
- Connection errors (network issues)
- Temporary server unavailability
- HTTP errors

## Features

### 1. Infinite Retries (Configurable)
- Default: 999,999 retries (effectively infinite)
- Configurable via `SDK_MAX_RETRIES` environment variable
- Will keep retrying until SDK becomes available

### 2. Exponential Backoff
- Retry delays increase exponentially: 5s → 10s → 20s → 40s → ...
- Prevents overwhelming the SDK server
- Configurable via `SDK_BACKOFF_FACTOR` and `SDK_RETRY_DELAY`

### 3. Increased Timeout
- Default timeout increased from 10s to 60s
- Gives SDK more time to respond
- Configurable via `SDK_TIMEOUT`

### 4. Better Error Logging
```
⚠️  [Timeout] SDK connection timed out (attempt 1). Retrying in 5.0s...
⚠️  [Connection Error] Cannot reach SDK at http://31.97.202.17:8080/v1/plate-reader/ (attempt 2). Retrying in 10.0s...
⚠️  [Request Error] Plate Recognizer request failed: ... (attempt 3). Retrying in 20.0s...
```

## Configuration

### Environment Variables (docker-compose.yml)

```yaml
environment:
  # SDK Connection
  SDK_URL: http://31.97.202.17:8080/v1/plate-reader/
  API_KEY: 4478d74ca90ad82a3a73bd309d8a0f4888bad9b8
  
  # Retry Configuration
  SDK_TIMEOUT: 60              # Request timeout (seconds)
  SDK_MAX_RETRIES: 999999      # Max retry attempts (effectively infinite)
  SDK_BACKOFF_FACTOR: 2        # Exponential backoff multiplier
  SDK_RETRY_DELAY: 5           # Initial retry delay (seconds)
```

### Customization Options

| Variable | Default | Description |
|----------|---------|-------------|
| `SDK_TIMEOUT` | 60 | Timeout per request (seconds) |
| `SDK_MAX_RETRIES` | 999999 | Maximum retry attempts |
| `SDK_BACKOFF_FACTOR` | 2 | Backoff multiplier (delay = base * factor^attempt) |
| `SDK_RETRY_DELAY` | 5 | Initial delay between retries (seconds) |

## Retry Behavior

### Retry Schedule Example:

| Attempt | Wait Time | Cumulative Time |
|---------|-----------|-----------------|
| 1 | 0s | 0s |
| 2 | 5s | 5s |
| 3 | 10s | 15s |
| 4 | 20s | 35s |
| 5 | 40s | 75s |
| 6 | 80s | 155s |
| 7 | 160s | 315s |
| ... | ... | ... |

### What Gets Retried:
✅ Connection timeouts
✅ Connection errors (network down)
✅ DNS resolution failures
✅ Server 500+ errors (via urllib3 retry)

### What Does NOT Get Retried:
❌ HTTP 400-level errors (bad request, unauthorized, etc.)
❌ Invalid JSON responses
❌ SDK returns error in response body

## How It Works

```python
def recognition_api(frame, retry_count=0):
    while True:  # Infinite retry loop
        try:
            session = create_retry_session()  # Session with urllib3 retry
            r = session.post(SDK_URL, files=files, headers=headers, timeout=SDK_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            # Wait and retry with exponential backoff
            wait_time = SDK_RETRY_DELAY * (SDK_BACKOFF_FACTOR ** retry_count)
            time.sleep(wait_time)
            retry_count += 1
        except requests.exceptions.ConnectionError:
            # Same retry logic for connection errors
        except requests.exceptions.HTTPError:
            # Don't retry HTTP errors, return empty dict
            return {}
```

## Rebuild and Deploy

### Step 1: Rebuild the Docker image
```bash
cd /home/katomaran/Desktop/g/lnpr
docker-compose build
```

### Step 2: Stop and remove old container
```bash
docker-compose down
```

### Step 3: Start with new configuration
```bash
docker-compose up -d
```

### Step 4: Monitor logs
```bash
docker-compose logs -f event_listener
```

## Expected Behavior

### When SDK is Unavailable:
```
🎬 Received new LPR clip message...
🎥 Saved incoming clip → /app/received_events/xxx.mp4
🔍 Running LPR processing on event xxx...
🎥 Starting LPR on /app/received_events/xxx.mp4
⚠️  [Connection Error] Cannot reach SDK at http://31.97.202.17:8080/v1/plate-reader/ (attempt 1). Retrying in 5.0s...
⚠️  [Connection Error] Cannot reach SDK at http://31.97.202.17:8080/v1/plate-reader/ (attempt 2). Retrying in 10.0s...
⚠️  [Connection Error] Cannot reach SDK at http://31.97.202.17:8080/v1/plate-reader/ (attempt 3). Retrying in 20.0s...
```

### When SDK Becomes Available:
```
⚠️  [Connection Error] Cannot reach SDK at http://31.97.202.17:8080/v1/plate-reader/ (attempt 10). Retrying in 2560.0s...
[Frame 10] Processed (1 active plates)  ← SDK is back!
[Frame 20] Processed (1 active plates)
✅ Done. Crops + CSV saved in /app/lnpr_outputs
```

## Troubleshooting

### Issue: Still getting immediate failures

**Solution**: Rebuild the image
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Issue: Retry delays are too short/long

**Solution**: Adjust environment variables in docker-compose.yml
```yaml
SDK_RETRY_DELAY: 10      # Start with 10s delay
SDK_BACKOFF_FACTOR: 1.5  # Slower exponential growth
```

### Issue: Want to limit retries

**Solution**: Set a specific max retry count
```yaml
SDK_MAX_RETRIES: 10  # Retry only 10 times
```

### Issue: SDK takes long to respond

**Solution**: Increase timeout
```yaml
SDK_TIMEOUT: 120  # Wait up to 2 minutes per request
```

## Network Connectivity Check

### Test if SDK is reachable:
```bash
# From host machine
curl -v http://31.97.202.17:8080/v1/plate-reader/

# From inside container
docker exec -it event_listener curl -v http://31.97.202.17:8080/v1/plate-reader/
```

### Check DNS resolution:
```bash
docker exec -it event_listener ping 31.97.202.17
docker exec -it event_listener nslookup 31.97.202.17
```

## Production Recommendations

1. **Monitor retry attempts**: If retries are consistently high, investigate SDK availability
2. **Set up SDK health monitoring**: Separate service to check SDK health
3. **Consider timeout alerts**: Alert if a single request takes > X attempts
4. **Log analysis**: Track retry patterns to identify recurring issues

## Alternative Solutions

If SDK continues to be unreachable:

1. **Check firewall rules**: Ensure port 8080 is accessible
2. **Verify SDK is running**: Check if SDK container/service is up
3. **Network connectivity**: Verify routing between containers
4. **Use internal networking**: If SDK is on same host, use Docker network
5. **VPN/Proxy**: If SDK is behind VPN, configure access

## Summary

✅ **Infinite retries implemented** (configurable)
✅ **Exponential backoff** prevents overwhelming the server
✅ **Increased timeout** from 10s to 60s
✅ **Better error logging** shows retry attempts
✅ **Handles all connection issues** (timeout, connection error, network issues)
✅ **No mock implementation** - real SDK integration maintained

The service will now keep trying to connect to the SDK indefinitely until it becomes available!

