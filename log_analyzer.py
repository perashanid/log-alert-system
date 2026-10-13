"""
Intelligent Log Analyzer
Scans logs and identifies genuine issues worth alerting
"""

import re
import json
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional
from collections import defaultdict


class LogAnalyzer:
    def __init__(self):
        # Error patterns to detect
        self.error_patterns = [
            r'\bERROR\b',
            r'\bCRITICAL\b',
            r'\bFATAL\b',
            r'\bEXCEPTION\b',
            r'Exception:',
            r'Traceback',
            r'stack trace',
            r'\b5\d{2}\b',  # 5xx status codes
            r'timeout',
            r'connection refused',
            r'connection reset',
            r'out of memory',
            r'OOMKilled',
            r'panic:',
            r'segmentation fault',
            r'core dumped'
        ]
        
        # Patterns to ignore (noise)
        self.noise_patterns = [
            r'health[_\s-]?check',
            r'healthz',
            r'readiness[_\s-]?probe',
            r'liveness[_\s-]?probe',
            r'/ping',
            r'/status',
            r'expected retry',
            r'retrying.*success',
            r'temporary.*resolv',
            r'WARN.*deprecated',
            r'INFO.*',
            r'DEBUG.*',
            r'connection pool.*waiting',  # Normal connection pool behavior
            r'rate limit.*normal',
        ]
        
        # Service name patterns
        self.service_patterns = [
            r'service[:\s]+([a-zA-Z0-9\-_]+)',
            r'\[([a-zA-Z0-9\-_]+)\]',
            r'/var/log/([a-zA-Z0-9\-_]+)',
            r'app[:\s]+([a-zA-Z0-9\-_]+)',
            r'container[:\s]+([a-zA-Z0-9\-_]+)',
        ]
        
        # Severity indicators
        self.critical_keywords = [
            'CRITICAL', 'FATAL', 'panic', 'OOMKilled', 
            'segmentation fault', 'core dumped', 'database down',
            'all instances down', 'cannot connect to database'
        ]
        
        self.high_keywords = [
            r'5\d{2}', 'Exception', 'connection refused',
            'connection reset', 'timeout', 'failed to', 'unable to'
        ]
    
    def is_error_line(self, line: str) -> bool:
        """Check if log line contains an error."""
        line_lower = line.lower()
        
        # Check for error patterns
        for pattern in self.error_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        
        return False
    
    def is_noise(self, line: str) -> bool:
        """Check if log line is known noise."""
        line_lower = line.lower()
        
        for pattern in self.noise_patterns:
            if re.search(pattern, line_lower):
                return True
        
        return False
    
    def extract_service_name(self, line: str) -> str:
        """Extract service name from log line."""
        for pattern in self.service_patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(1)
        
        return "unknown"
    
    def extract_timestamp(self, line: str) -> Optional[str]:
        """Extract timestamp from log line."""
        # Common timestamp patterns
        patterns = [
            r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}',  # ISO format
            r'\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}',       # Apache format
            r'\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}',       # Syslog format
        ]
        
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(0)
        
        return datetime.now().isoformat()
    
    def determine_severity(self, line: str) -> str:
        """Determine severity level of error."""
        line_lower = line.lower()
        
        # Check for critical indicators
        for keyword in self.critical_keywords:
            if re.search(keyword, line_lower):
                return "Critical"
        
        # Check for high severity indicators
        for keyword in self.high_keywords:
            if re.search(keyword, line_lower):
                return "High"
        
        return "Medium"
    
    def create_error_signature(self, line: str) -> str:
        """
        Create a signature for error deduplication.
        Removes timestamps, IDs, and specific values.
        """
        # Remove timestamps
        signature = re.sub(r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(\.\d+)?', '', line)
        
        # Remove common IDs and numbers
        signature = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', 'UUID', signature)
        signature = re.sub(r'\bid[:\s]+\d+', 'id:ID', signature)
        signature = re.sub(r'request[_\s]id[:\s]+\S+', 'request_id:ID', signature)
        signature = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', 'IP', signature)
        
        # Remove variable numbers but keep error codes
        signature = re.sub(r'(?<!status[:\s])(?<!code[:\s])\b\d{4,}\b', 'NUM', signature)
        
        return signature.strip()
    
    def extract_error_summary(self, line: str) -> str:
        """Extract clear, concise error summary."""
        # Remove timestamp prefix
        summary = re.sub(r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(\.\d+)?\s*', '', line)
        summary = re.sub(r'^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+', '', summary)
        
        # Remove log level prefix
        summary = re.sub(r'^\[?(ERROR|CRITICAL|FATAL|WARN|INFO)\]?\s*[:\s]*', '', summary, flags=re.IGNORECASE)
        
        # Extract the core message (first sentence or up to 150 chars)
        if '.' in summary[:200]:
            summary = summary.split('.')[0] + '.'
        else:
            summary = summary[:150]
        
        # Clean up
        summary = ' '.join(summary.split())  # Normalize whitespace
        
        # Ensure it's a complete sentence
        if summary and not summary.endswith('.'):
            summary += '.'
        
        return summary
    
    def analyze_logs(
        self,
        log_lines: List[str],
        recent_errors: List[str] = None
    ) -> Dict:
        """
        Analyze a batch of log lines and identify genuine issues.
        
        Args:
            log_lines: List of raw log lines
            recent_errors: List of error signatures seen in last hour (for deduplication)
            
        Returns:
            Dictionary with alerts array
        """
        if recent_errors is None:
            recent_errors = []
        
        # Convert to set for faster lookup
        recent_error_set = set(recent_errors)
        
        # Group errors by signature
        error_groups = defaultdict(list)
        
        for line in log_lines:
            # Skip empty lines
            if not line.strip():
                continue
            
            # Check if it's an error
            if not self.is_error_line(line):
                continue
            
            # Check if it's noise
            if self.is_noise(line):
                continue
            
            # Create error signature for deduplication
            signature = self.create_error_signature(line)
            
            # Skip if we've seen this recently
            if signature in recent_error_set:
                continue
            
            # Group by signature
            error_groups[signature].append(line)
        
        # Create alerts from grouped errors
        alerts = []
        
        for signature, lines in error_groups.items():
            # Use first occurrence for details
            first_line = lines[0]
            
            alert = {
                "severity": self.determine_severity(first_line),
                "service_name": self.extract_service_name(first_line),
                "error_summary": self.extract_error_summary(first_line),
                "first_seen_timestamp": self.extract_timestamp(first_line),
                "occurrence_count": len(lines),
                "error_signature": signature,
                "sample_log": first_line[:200]  # Include sample for debugging
            }
            
            alerts.append(alert)
        
        # Sort by severity (Critical first, then High, then Medium)
        severity_order = {"Critical": 0, "High": 1, "Medium": 2}
        alerts.sort(key=lambda x: (severity_order.get(x['severity'], 3), -x['occurrence_count']))
        
        return {"alerts": alerts}


def analyze_logs_from_list(
    log_lines: List[str],
    recent_errors: List[str] = None
) -> str:
    """
    Main function to analyze logs and return JSON.
    
    Args:
        log_lines: List of log lines
        recent_errors: List of recent error signatures (optional)
        
    Returns:
        JSON string with alerts
    """
    analyzer = LogAnalyzer()
    result = analyzer.analyze_logs(log_lines, recent_errors)
    return json.dumps(result, indent=2)


def analyze_logs_from_json(json_input: str) -> str:
    """
    Analyze logs from JSON input.
    
    Expected format:
    {
        "log_lines": ["line1", "line2", ...],
        "recent_errors": ["sig1", "sig2", ...] (optional)
    }
    """
    data = json.loads(json_input)
    return analyze_logs_from_list(
        log_lines=data['log_lines'],
        recent_errors=data.get('recent_errors', [])
    )


if __name__ == "__main__":
    # Example log batch
    sample_logs = [
        "2026-07-27 19:00:01 [payment-service] INFO Starting payment processing",
        "2026-07-27 19:00:02 [payment-service] ERROR Failed to connect to database: connection refused at 10.0.0.5:5432",
        "2026-07-27 19:00:03 [payment-service] ERROR Failed to connect to database: connection refused at 10.0.0.5:5432",
        "2026-07-27 19:00:05 [api-gateway] CRITICAL Panic: runtime error: index out of range [5] with length 3",
        "2026-07-27 19:00:06 [user-service] WARN Deprecated API call from client v1.2.0",
        "2026-07-27 19:00:07 [load-balancer] INFO Health check /healthz returned 200",
        "2026-07-27 19:00:10 [order-service] ERROR HTTP 503 Service Unavailable - downstream timeout after 30s",
        "2026-07-27 19:00:11 [order-service] ERROR HTTP 503 Service Unavailable - downstream timeout after 30s",
        "2026-07-27 19:00:12 [order-service] ERROR HTTP 503 Service Unavailable - downstream timeout after 30s",
        "2026-07-27 19:00:15 [auth-service] FATAL OOMKilled: container exceeded memory limit",
        "2026-07-27 19:00:20 [notification-service] INFO Email sent successfully to user@example.com",
        "2026-07-27 19:00:25 [cache-service] ERROR Connection reset by peer while reading response",
        "2026-07-27 19:00:30 [api-gateway] INFO Request processed in 45ms",
        "2026-07-27 19:00:35 [payment-service] Exception in thread 'main': NullPointerException at PaymentProcessor.java:142",
        "",
        "2026-07-27 19:00:40 [monitoring] INFO Readiness probe succeeded",
    ]
    
    print("=" * 80)
    print("LOG ANALYZER - Example Analysis")
    print("=" * 80)
    print()
    
    print(f"Analyzing {len(sample_logs)} log lines...")
    print()
    
    result = analyze_logs_from_list(sample_logs)
    
    print(result)
    
    # Example with recent errors (deduplication)
    print("\n\n" + "=" * 80)
    print("DEDUPLICATION EXAMPLE")
    print("=" * 80)
    print()
    
    # Simulate that we've seen the database connection error recently
    recent_errors = [
        "ERROR Failed to connect to database connection refused at IP"
    ]
    
    print("Recent errors (from last hour):")
    for err in recent_errors:
        print(f"  - {err}")
    print()
    
    result_with_dedup = analyze_logs_from_list(sample_logs, recent_errors)
    result_data = json.loads(result_with_dedup)
    
    print(f"Alerts after deduplication: {len(result_data['alerts'])}")
    print()
    print(result_with_dedup)
