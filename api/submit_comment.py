import json
import os
import time
import hmac
import hashlib
import base64
import urllib.request
from http.server import BaseHTTPRequestHandler

# Secure secret key for signing comment tokens (can be set via env, otherwise fallback)
SECRET_KEY = os.environ.get("COMMENT_SECRET_KEY", "tuj-default-secure-key-987654321").encode("utf-8")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

def sign_data(data):
    serialized = json.dumps(data).encode("utf-8")
    signature = hmac.new(SECRET_KEY, serialized, hashlib.sha256).hexdigest()
    payload = {
        "data": base64.b64encode(serialized).decode("utf-8"),
        "sig": signature
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            post_id = data.get('post_id')
            author = data.get('author', '').strip()
            email = data.get('email', '').strip()
            comment = data.get('comment', '').strip()
            
            if not all([post_id, author, email, comment]):
                raise ValueError("All fields (post_id, author, email, comment) are required.")
                
            # Create signing payload
            payload = {
                "post_id": post_id,
                "author": author,
                "email": email,
                "comment": comment,
                "timestamp": int(time.time())
            }
            
            token = sign_data(payload)
            host = self.headers.get('Host', 'localhost:8000')
            proto = 'https' if not host.startswith('localhost') else 'http'
            verification_url = f"{proto}://{host}/api/verify_comment?token={token}"
            
            # Send verification email via Resend API
            if RESEND_API_KEY:
                email_body = {
                    "from": "The Urban Journal <noreply@the-urban-journal.com>",
                    "to": email,
                    "subject": "Verify your comment on The Urban Journal",
                    "html": f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 8px;">
                        <h2 style="color: #111; font-family: 'Times New Roman', serif;">Verify Your Comment</h2>
                        <p>Hello {author},</p>
                        <p>Thank you for sharing your thoughts on The Urban Journal. Please click the button below to verify your email and submit your comment for moderation:</p>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{verification_url}" style="background: #111; color: #fff; text-decoration: none; padding: 12px 24px; font-weight: bold; border-radius: 4px; display: inline-block;">Verify Comment</a>
                        </div>
                        <p style="font-size: 13px; color: #666;">If the button above does not work, copy and paste this link into your browser:</p>
                        <p style="font-size: 13px; color: #0073aa; word-break: break-all;">{verification_url}</p>
                        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
                        <p style="font-size: 12px; color: #999;">If you did not write this comment, you can safely ignore this email.</p>
                    </div>
                    """
                }
                
                req = urllib.request.Request(
                    "https://api.resend.com/emails",
                    data=json.dumps(email_body).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {RESEND_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req) as response:
                    response.read()
            else:
                # Local development/fallback log
                print(f"[DEVELOPMENT] Verification Link: {verification_url}")
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            
        except Exception as e:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "message": str(e)}).encode('utf-8'))
