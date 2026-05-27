from flask import Flask, request, Response
import requests
import threading
import time
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

PASTEBIN_URL = "https://pastebin.com/raw/dqhqf4kW"
TARGET_BASE = "https://pwthor.live"
COOKIE_REFRESH_SEC = 1800  # 30 minutes

cookies_cache = {}
cookie_lock = threading.Lock()

def fetch_cookies():
    """Fetch and parse cookies from Pastebin. Returns dict."""
    try:
        resp = requests.get(PASTEBIN_URL, timeout=10)
        resp.raise_for_status()
        raw = resp.text.strip()
        if '=' in raw:
            key, value = raw.split('=', 1)
            app.logger.info(f"Fetched cookie: {key}={value[:10]}...")
            return {key: value}
        else:
            app.logger.warning("Cookie format unexpected: %s", raw)
    except Exception as e:
        app.logger.error("Failed to fetch cookies: %s", e)
    return {}

def update_cookies_loop():
    """Background thread that refreshes cookies periodically."""
    global cookies_cache
    while True:
        new_cookies = fetch_cookies()
        with cookie_lock:
            cookies_cache = new_cookies
        time.sleep(COOKIE_REFRESH_SEC)

# Start the background thread
threading.Thread(target=update_cookies_loop, daemon=True).start()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def proxy(path):
    # Build the target URL
    target_url = f"{TARGET_BASE}/{path}"
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"

    # Forward headers (exclude 'Host' to avoid conflicts)
    headers = {k: v for k, v in request.headers if k.lower() != 'host'}
    # Add cookies from Pastebin
    with cookie_lock:
        cookies = cookies_cache.copy()

    app.logger.info(f"Proxying {request.method} {target_url} with cookies {cookies}")

    try:
        # Forward the request
        upstream = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            cookies=cookies,
            data=request.get_data(),
            allow_redirects=False,
            timeout=20
        )
    except requests.RequestException as e:
        app.logger.error("Upstream error: %s", e)
        return Response("Upstream request failed", status=502)

    # Build response
    response = Response(upstream.content, status=upstream.status_code)
    # Copy headers except hop-by-hop ones
    for k, v in upstream.headers.items():
        if k.lower() not in ['transfer-encoding', 'content-encoding', 'content-length']:
            response.headers[k] = v
    return response

if __name__ == '__main__':
    # For local testing; Render uses gunicorn
    app.run(host='0.0.0.0', port=5000)
