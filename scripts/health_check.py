#!/usr/bin/env python3
"""
IMDF Health Check Script — systemd Watchdog Companion
======================================================
Independently checks if the IMDF API service is healthy.
Used by systemd ExecStartPost and watchdog-integrated monitoring.

Usage:
    python3 scripts/health_check.py [--port PORT] [--timeout SECONDS]

Exit codes:
    0 — Service is healthy (HTTP 200)
    1 — Service is unhealthy or unreachable
    2 — Script usage error
"""

import sys
import time
import argparse
import urllib.request
import urllib.error
import json
import os


def check_health(host: str = "localhost", port: int = 8765, timeout: int = 5) -> dict:
    """
    Perform a health check against the IMDF API.

    Returns:
        dict with keys: healthy (bool), status_code (int), body (dict), error (str|None)
    """
    url = f"http://{host}:{port}/api/v1/health"
    result = {
        "healthy": False,
        "status_code": 0,
        "body": {},
        "error": None,
    }

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "IMDF-HealthCheck/1.0")

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result["status_code"] = resp.status
            body_bytes = resp.read()
            if resp.status == 200:
                try:
                    result["body"] = json.loads(body_bytes.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    result["body"] = {"raw": body_bytes.decode("utf-8", errors="replace")[:200]}

                # Verify the response looks like a health check
                status = result["body"].get("status", "")
                if status == "ok":
                    result["healthy"] = True
                else:
                    result["error"] = f"Health endpoint returned status={status}, expected 'ok'"
            else:
                result["error"] = f"HTTP {resp.status} from health endpoint"

    except urllib.error.URLError as e:
        result["error"] = f"Connection failed: {e.reason}"
    except urllib.error.HTTPError as e:
        result["status_code"] = e.code
        result["error"] = f"HTTP error {e.code}: {e.reason}"
    except Exception as e:
        result["error"] = f"Unexpected error: {type(e).__name__}: {e}"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="IMDF Health Check Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/health_check.py
  python3 scripts/health_check.py --port 8765 --timeout 10
  python3 scripts/health_check.py --retry 5 --retry-delay 2

Exit codes:
  0 — healthy, 1 — unhealthy, 2 — usage error
        """,
    )
    parser.add_argument(
        "--host", default=os.environ.get("IMDF_WEB_HOST", "localhost"),
        help="Host to check (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int,
        default=int(os.environ.get("IMDF_WEB_PORT", "8765")),
        help="Port to check (default: 8765)"
    )
    parser.add_argument(
        "--timeout", type=int, default=5,
        help="HTTP request timeout in seconds (default: 5)"
    )
    parser.add_argument(
        "--retry", type=int, default=1,
        help="Number of retries on failure (default: 1)"
    )
    parser.add_argument(
        "--retry-delay", type=int, default=2,
        help="Delay between retries in seconds (default: 2)"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress output (use only exit code)"
    )

    args = parser.parse_args()

    last_error = None
    for attempt in range(1, args.retry + 1):
        if not args.quiet:
            print(f"[{attempt}/{args.retry}] Checking http://{args.host}:{args.port}/api/v1/health ...",
                  end=" ", flush=True)

        result = check_health(args.host, args.port, args.timeout)

        if result["healthy"]:
            if not args.quiet:
                print("OK")
                body_version = result["body"].get("version", "unknown")
                print(f"  Service: {result['body'].get('service', 'imdf')} v{body_version}")
            sys.exit(0)

        last_error = result["error"]
        if not args.quiet:
            print(f"FAILED — {result['error']}")

        if attempt < args.retry:
            if not args.quiet:
                print(f"  Retrying in {args.retry_delay}s...")
            time.sleep(args.retry_delay)

    if not args.quiet:
        print(f"Health check FAILED after {args.retry} attempt(s): {last_error}",
              file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
