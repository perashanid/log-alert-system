# Intelligent Log Alert System

Stop drowning in log noise! This system scans application logs and only alerts you about genuine problems.

## 🎯 What It Does

**Scans logs for real problems:**
- ✅ Errors, exceptions, crashes, timeouts
- ✅ 5xx status codes, connection failures
- ✅ Out of memory, panics, segfaults

**Filters out noise:**
- ❌ Health check logs
- ❌ Expected retries
- ❌ Routine warnings
- ❌ Duplicate errors (seen in last hour)

**Smart alerting:**
- **Critical** → SMS + Slack + Create incident
- **High** → Slack ping
- **Medium** → Log only, no ping

## 📋 Example

**Input logs:**
```
2026-07-27 19:00:02 [payment-service] ERROR Failed to connect to database
2026-07-27 19:00:05 [api-gateway] CRITICAL Panic: index out of range
2026-07-27 19:00:07 [load-balancer] INFO Health check /healthz returned 200
2026-07-27 19:00:10 [order-service] ERROR HTTP 503 timeout after 30s
2026-07-27 19:00:15 [auth-service] FATAL OOMKilled: memory limit exceeded
```

**Output alerts:**
```json
{
  "alerts": [
    {
      "severity": "Critical",
      "service_name": "api-gateway",
      "error_summary": "Panic: index out of range.",
      "occurrence_count": 1
    },
    {
      "severity": "High",
      "service_name": "order-service",
      "error_summary": "HTTP 503 timeout after 30s.",
      "occurrence_count": 1
    }
  ]
}
```

Health check log is **automatically filtered** as noise.

## 🚀 Quick Start

```bash
cd log-alert-system
pip install -r requirements.txt
python log_analyzer.py
```

You'll see analysis of sample logs with different severity levels.

## 🔧 Usage

### Python API

```python
from log_analyzer import analyze_logs_from_list

logs = [
    "2026-07-27 ERROR Database connection failed",
    "2026-07-27 CRITICAL Out of memory",
    "2026-07-27 INFO Health check passed"
]

result = analyze_logs_from_list(logs)
print(result)  # JSON with alerts array
```

### With Deduplication

```python
# Track errors seen in last hour
recent_errors = [
    "ERROR Database connection failed"  # This error signature
]

# Won't alert on duplicates
result = analyze_logs_from_list(logs, recent_errors)
```

## 📊 Severity Levels

### Critical (SMS + Slack + Incident)
- CRITICAL, FATAL, panic
- OOMKilled, segmentation fault
- Database completely down
- All instances down

### High (Slack ping)
- ERROR, Exception
- 5xx status codes
- Connection refused/reset
- Timeouts, failed operations

### Medium (Log only)
- Everything else that's an error
- Lower priority failures

## 🔔 Automation Setup

### Option 1: Make.com

**Modules:**
1. **Schedule** - Every 5-15 minutes
2. **HTTP/CloudWatch** - Fetch recent logs
3. **HTTP POST** - Send to analyzer
4. **Filter** - Only if alerts.length > 0
5. **Router** by severity:
   - **Critical** → Twilio SMS + Slack + PagerDuty
   - **High** → Slack #incidents
   - **Medium** → Google Sheets log only
6. **Google Sheets** - Log all alerts

**See `automation_configs.json` for complete setup.**

### Option 2: AWS Lambda + CloudWatch

```python
import boto3
from log_analyzer import analyze_logs_from_list

def lambda_handler(event, context):
    # Get logs from CloudWatch
    logs_client = boto3.client('logs')
    
    # Fetch log events
    response = logs_client.filter_log_events(
        logGroupName='/aws/lambda/my-app',
        startTime=int((datetime.now() - timedelta(minutes=15)).timestamp() * 1000)
    )
    
    log_lines = [event['message'] for event in response['events']]
    
    # Analyze
    result = analyze_logs_from_list(log_lines)
    alerts = json.loads(result)['alerts']
    
    # Send alerts
    for alert in alerts:
        if alert['severity'] == 'Critical':
            send_sms(alert)
            create_incident(alert)
        send_slack(alert)
    
    return {'statusCode': 200}
```

### Option 3: GitHub Actions (for app logs)

```yaml
name: Monitor Logs

on:
  schedule:
    - cron: '*/15 * * * *'  # Every 15 minutes

jobs:
  check-logs:
    runs-on: ubuntu-latest
    steps:
      - name: Fetch logs
        run: |
          # Fetch from logging service
          curl -H "Authorization: Bearer ${{ secrets.LOG_TOKEN }}" \
            https://logs.example.com/api/recent > logs.txt
      
      - name: Analyze
        run: |
          python log_analyzer.py --input logs.txt --output alerts.json
      
      - name: Alert if needed
        run: |
          # Send to Slack if alerts found
```

## 🎨 Customization

### Add Custom Error Patterns

```python
analyzer = LogAnalyzer()

# Add your patterns
analyzer.error_patterns.append(r'custom error pattern')
analyzer.critical_keywords.append('your critical keyword')
```

### Add Noise Patterns

```python
# Ignore specific patterns
analyzer.noise_patterns.append(r'expected maintenance window')
analyzer.noise_patterns.append(r'planned downtime')
```

### Custom Service Detection

```python
analyzer.service_patterns.append(r'my-app-([a-z]+)-service')
```

## 📈 Integration Examples

### Slack Webhook

```python
import requests

def send_slack_alert(alert):
    severity_emoji = {
        'Critical': ':rotating_light:',
        'High': ':warning:',
        'Medium': ':information_source:'
    }
    
    message = {
        "text": f"{severity_emoji[alert['severity']]} *{alert['severity']} Alert*",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Service:* {alert['service_name']}\n*Error:* {alert['error_summary']}\n*Count:* {alert['occurrence_count']}"
                }
            }
        ]
    }
    
    requests.post(SLACK_WEBHOOK_URL, json=message)
```

### Twilio SMS (Critical only)

```python
from twilio.rest import Client

def send_sms_alert(alert):
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    
    message = client.messages.create(
        body=f"CRITICAL: {alert['service_name']} - {alert['error_summary']}",
        from_='+1234567890',
        to='+0987654321'
    )
```

### PagerDuty Incident

```python
def create_pagerduty_incident(alert):
    requests.post(
        'https://api.pagerduty.com/incidents',
        headers={
            'Authorization': f'Token token={PAGERDUTY_API_KEY}',
            'Content-Type': 'application/json'
        },
        json={
            'incident': {
                'type': 'incident',
                'title': f"{alert['service_name']}: {alert['error_summary']}",
                'service': {'id': SERVICE_ID, 'type': 'service_reference'},
                'urgency': 'high' if alert['severity'] == 'Critical' else 'low'
            }
        }
    )
```

## 🧪 Testing

Run test suite:
```bash
python test_log_analyzer.py
```

Test with your logs:
```python
from log_analyzer import analyze_logs_from_list

# Your actual logs
my_logs = [
    # paste log lines here
]

result = analyze_logs_from_list(my_logs)
print(result)
```

## 💡 Best Practices

1. **Start with higher thresholds** - Don't alert on everything initially

2. **Build noise list gradually** - Add patterns as you see false positives

3. **Track deduplication** - Store recent errors in Redis or database

4. **Set up runbooks** - Link each alert type to resolution steps

5. **Monitor alert fatigue** - If getting too many, increase thresholds

6. **Use different channels** - Critical → phone, High → Slack, Medium → log only

7. **Include context** - Service name, timestamp, occurrence count help triage

## 📊 Metrics to Track

- Total logs scanned per hour
- Errors detected vs filtered as noise
- False positive rate
- Time to resolution per alert type
- Alert volume by service

## 🔐 Security

- **Never log sensitive data** (passwords, tokens, PII)
- **Sanitize before sending** to external services
- **Encrypt logs at rest** and in transit
- **Access control** on who can see alerts
- **Audit trail** of who acknowledged alerts

## 🐛 Troubleshooting

### Getting Too Many Alerts

**Solution:**
- Add more noise patterns
- Increase deduplication window (1h → 4h)
- Raise severity thresholds

### Missing Important Errors

**Solution:**
- Check error patterns are comprehensive
- Verify logs are being fetched
- Ensure error isn't matching noise pattern

### Duplicate Alerts

**Solution:**
- Verify deduplication is enabled
- Check error signatures are normalized correctly
- Increase deduplication window

## 📄 License

MIT License

---

**Stop reacting to noise. Start fixing real problems.** 🚀
