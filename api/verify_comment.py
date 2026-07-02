import os
import json
import html as html_mod
import time
import hmac
import hashlib
import base64
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler

# Secret key — MUST be set via environment variable
_secret_raw = os.environ.get("COMMENT_SECRET_KEY", "")
if not _secret_raw:
    print("WARNING: COMMENT_SECRET_KEY is not set. Comment verification will be disabled.")
SECRET_KEY = _secret_raw.encode("utf-8") if _secret_raw else None
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "simpliarjun/the_urban_journal")

# Token expiry: 24 hours
TOKEN_MAX_AGE_SECONDS = 24 * 60 * 60

def verify_data(token):
    if not SECRET_KEY:
        return None
    try:
        payload = json.loads(base64.b64decode(token.encode("utf-8")).decode("utf-8"))
        serialized = base64.b64decode(payload["data"].encode("utf-8"))
        expected_sig = hmac.new(SECRET_KEY, serialized, hashlib.sha256).hexdigest()
        if hmac.compare_digest(payload["sig"], expected_sig):
            data = json.loads(serialized.decode("utf-8"))
            # Check token expiry
            token_ts = data.get("timestamp", 0)
            if (int(time.time()) - token_ts) > TOKEN_MAX_AGE_SECONDS:
                return None  # Token expired
            return data
    except Exception:
        return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse query parameters
        parsed_url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_url.query)
        token = params.get('token', [None])[0]
        
        if not token:
            self.send_error_response("Verification token is missing.")
            return
            
        comment_data = verify_data(token)
        if not comment_data:
            self.send_error_response("Invalid or expired verification token. Tokens are valid for 24 hours.")
            return
            
        # Add verification timestamp
        comment_data["verified_at"] = int(time.time())
        
        filename = f"pending_comments/comment_{comment_data['post_id']}_{int(time.time())}.json"
        
        try:
            if GITHUB_TOKEN:
                # Production: Write directly to GitHub repository via API
                url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
                content_bytes = json.dumps(comment_data, indent=2).encode('utf-8')
                content_b64 = base64.b64encode(content_bytes).decode('utf-8')
                
                body = {
                    "message": f"Add verified comment by {comment_data['author']}",
                    "content": content_b64
                }
                
                req = urllib.request.Request(
                    url,
                    data=json.dumps(body).encode('utf-8'),
                    headers={
                        "Authorization": f"token {GITHUB_TOKEN}",
                        "Accept": "application/vnd.github.v3+json",
                        "Content-Type": "application/json",
                        "User-Agent": "The-Urban-Journal-Verify"
                    },
                    method="PUT"
                )
                with urllib.request.urlopen(req) as res:
                    res.read()
            else:
                # Local development: Write to local pending_comments folder
                os.makedirs("pending_comments", exist_ok=True)
                local_path = os.path.join(os.getcwd(), filename)
                with open(local_path, "w", encoding="utf-8") as f:
                    json.dump(comment_data, f, indent=2)
            
            # Send HTML success response
            self.send_success_response(comment_data['author'])
            
        except Exception as e:
            self.send_error_response(f"Failed to submit comment to queue: {str(e)}")

    def send_success_response(self, author):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Comment Verified - The Urban Journal</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f9f9f9; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .card {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); text-align: center; max-width: 400px; border: 1px solid #eaeaea; }}
                h1 {{ font-family: 'Times New Roman', Times, serif; color: #111; margin-bottom: 15px; }}
                p {{ color: #555; line-height: 1.6; font-size: 15px; margin-bottom: 25px; }}
                .btn {{ background: #111; color: white; text-decoration: none; padding: 12px 24px; font-weight: bold; border-radius: 4px; display: inline-block; transition: background 0.2s; }}
                .btn:hover {{ background: #333; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>Thank You, {html_mod.escape(author)}!</h1>
                <p>Your email has been verified and your comment has been submitted to the moderation queue. It will appear on the website once approved by the administrator.</p>
                <a href="/" class="btn">Go to Home</a>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def send_error_response(self, error_message):
        self.send_response(400)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Verification Error - The Urban Journal</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f9f9f9; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .card {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); text-align: center; max-width: 400px; border: 1px solid #f5c6cb; }}
                h1 {{ font-family: 'Times New Roman', Times, serif; color: #721c24; margin-bottom: 15px; }}
                p {{ color: #721c24; line-height: 1.6; font-size: 15px; margin-bottom: 25px; }}
                .btn {{ background: #721c24; color: white; text-decoration: none; padding: 12px 24px; font-weight: bold; border-radius: 4px; display: inline-block; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>Verification Failed</h1>
                <p>{html_mod.escape(error_message)}</p>
                <a href="/" class="btn" style="background: #111;">Go to Home</a>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))
