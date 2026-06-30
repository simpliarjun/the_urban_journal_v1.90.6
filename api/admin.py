import os
import json
import base64
import sqlite3
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

# Database path — bundled in the deployment (read-only)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup.db")


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


def _get_pending_comments_from_github():
    """Fetch pending comment JSON files from the GitHub repo."""
    pending = []
    if not GITHUB_TOKEN:
        return pending

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/pending_comments"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TUJ-Admin",
        },
    )
    try:
        with urllib.request.urlopen(req) as res:
            files = json.loads(res.read().decode("utf-8"))

        for f in files:
            if not f["name"].endswith(".json"):
                continue
            # Fetch file content
            file_req = urllib.request.Request(
                f["download_url"],
                headers={"User-Agent": "TUJ-Admin"},
            )
            with urllib.request.urlopen(file_req) as file_res:
                comment_data = json.loads(file_res.read().decode("utf-8"))
                comment_data["filename"] = f["name"]
                comment_data["sha"] = f["sha"]
                pending.append(comment_data)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"GitHub API error: {e}")
    except Exception as e:
        print(f"Error fetching pending comments: {e}")

    return pending


def _get_approved_comments_from_db():
    """Fetch approved comments from the bundled SQLite database."""
    approved = []
    if not os.path.exists(DB_PATH):
        # Fallback: read from GitHub approved_comments/approved.json
        return _get_approved_comments_from_github()

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.comment_ID, c.comment_author, c.comment_author_email,
                   c.comment_content, c.comment_date, p.post_title
            FROM wp_comments c
            JOIN wp_posts p ON c.comment_post_ID = p.ID
            WHERE c.comment_approved = 1
            ORDER BY c.comment_date DESC
            """
        )
        for row in cursor.fetchall():
            approved.append(
                {
                    "id": row[0],
                    "author": row[1],
                    "email": row[2],
                    "comment": row[3],
                    "date": row[4],
                    "post_title": row[5],
                }
            )
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")

    return approved


def _get_approved_comments_from_github():
    """Fallback: fetch approved comments from GitHub repo's approved_comments/approved.json."""
    approved = []
    if not GITHUB_TOKEN:
        return approved

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/approved_comments/approved.json"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TUJ-Admin",
        },
    )
    try:
        with urllib.request.urlopen(req) as res:
            file_info = json.loads(res.read().decode("utf-8"))
            content = base64.b64decode(file_info["content"]).decode("utf-8")
            approved_list = json.loads(content)
            for idx, c in enumerate(approved_list):
                approved.append({
                    "id": idx,
                    "author": c.get("author", ""),
                    "email": c.get("email", ""),
                    "comment": c.get("comment", ""),
                    "date": c.get("date", ""),
                    "post_title": f"Post #{c.get('post_id', 'unknown')}",
                })
    except urllib.error.HTTPError:
        pass
    except Exception as e:
        print(f"Error reading approved comments from GitHub: {e}")

    return approved


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Check auth
        auth_header = self.headers.get("Authorization")
        if not _is_authorized(auth_header):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Admin Area"')
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Authentication required")
            return

        # Return pending + approved comments as JSON
        pending = _get_pending_comments_from_github()
        approved = _get_approved_comments_from_db()

        response_data = {"pending": pending, "approved": approved}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode("utf-8"))
