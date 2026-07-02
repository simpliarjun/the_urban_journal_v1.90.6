import os
import json
import hmac
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
        return user in ADMIN_EMAILS and hmac.compare_digest(pwd, ADMIN_PASS)
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

            if not filename:
                raise ValueError("Filename is required.")

            if not GITHUB_TOKEN:
                raise ValueError("GITHUB_TOKEN environment variable not set.")

            # 1. Read the pending comment file from GitHub
            file_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/pending_comments/{filename}"
            file_info = _github_api(file_url)
            comment_content = base64.b64decode(file_info["content"]).decode("utf-8")
            comment_data = json.loads(comment_content)
            file_sha = file_info["sha"]

            # 2. Read the current approved_comments data file (or create it)
            approved_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/approved_comments/approved.json"
            try:
                approved_info = _github_api(approved_url)
                approved_content = base64.b64decode(approved_info["content"]).decode("utf-8")
                approved_list = json.loads(approved_content)
                approved_sha = approved_info["sha"]
            except urllib.error.HTTPError:
                approved_list = []
                approved_sha = None

            # 3. Add the comment to the approved list
            import datetime
            approved_comment = {
                "author": comment_data["author"],
                "email": comment_data["email"],
                "comment": comment_data["comment"],
                "post_id": comment_data["post_id"],
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            approved_list.append(approved_comment)

            # 4. Write updated approved_comments file to GitHub
            new_content = base64.b64encode(
                json.dumps(approved_list, indent=2).encode("utf-8")
            ).decode("utf-8")
            update_data = {
                "message": f"Approve comment by {comment_data['author']}",
                "content": new_content,
            }
            if approved_sha:
                update_data["sha"] = approved_sha
            _github_api(approved_url, method="PUT", data=update_data)

            # 5. Delete the pending comment file from GitHub
            delete_data = {
                "message": f"Remove pending comment {filename}",
                "sha": file_sha,
            }
            _github_api(file_url, method="DELETE", data=delete_data)

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
