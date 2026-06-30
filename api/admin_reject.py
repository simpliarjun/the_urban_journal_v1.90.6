import os
import json
import base64
import urllib.request
from http.server import BaseHTTPRequestHandler

# Auth credentials from environment variables
ADMIN_EMAILS = [
    os.environ.get("ADMIN_EMAIL_1", ""),
    os.environ.get("ADMIN_EMAIL_2", ""),
]
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "simpliarjun/the_urban_journal_v1.90.6")


def _is_authorized(auth_header):
    """Verify Basic Auth credentials."""
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
        user, pwd = decoded.split(":", 1)
        return user in ADMIN_EMAILS and pwd == ADMIN_PASS
    except Exception:
        return False


def _github_api(url, method="GET", data=None):
    """Make a GitHub API request."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "TUJ-Admin",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode("utf-8"))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Check auth
        auth_header = self.headers.get("Authorization")
        if not _is_authorized(auth_header):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Admin Area"')
            self.end_headers()
            self.wfile.write(b"Authentication required")
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            filename = data.get("filename")
            comment_id = data.get("id")

            if not GITHUB_TOKEN:
                raise ValueError("GITHUB_TOKEN environment variable not set.")

            if filename:
                # Reject a pending comment — delete file from GitHub repo
                file_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/pending_comments/{filename}"
                file_info = _github_api(file_url)
                file_sha = file_info["sha"]

                delete_data = {
                    "message": f"Reject pending comment: {filename}",
                    "sha": file_sha,
                }
                _github_api(file_url, method="DELETE", data=delete_data)

            elif comment_id:
                # Delete an approved comment — remove from approved_comments/approved.json
                approved_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/approved_comments/approved.json"
                try:
                    approved_info = _github_api(approved_url)
                    approved_content = base64.b64decode(approved_info["content"]).decode("utf-8")
                    approved_list = json.loads(approved_content)
                    approved_sha = approved_info["sha"]

                    # Remove comment by index (id is used as index here)
                    comment_id_int = int(comment_id)
                    if 0 <= comment_id_int < len(approved_list):
                        approved_list.pop(comment_id_int)

                    new_content = base64.b64encode(
                        json.dumps(approved_list, indent=2).encode("utf-8")
                    ).decode("utf-8")
                    update_data = {
                        "message": "Delete approved comment",
                        "content": new_content,
                        "sha": approved_sha,
                    }
                    _github_api(approved_url, method="PUT", data=update_data)
                except urllib.error.HTTPError:
                    raise ValueError("No approved comments found.")
            else:
                raise ValueError("Either filename or id is required.")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"success": False, "message": str(e)}).encode("utf-8")
            )
