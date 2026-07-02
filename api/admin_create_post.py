import os
import re
import json
import hmac
import base64
import datetime
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler

ADMIN_EMAILS = [
    os.environ.get("ADMIN_EMAIL_1", ""),
    os.environ.get("ADMIN_EMAIL_2", ""),
]
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "simpliarjun/the_urban_journal_v1.90.6")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")


def _is_authorized(auth_header):
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
        user, pwd = decoded.split(":", 1)
        return user in ADMIN_EMAILS and hmac.compare_digest(pwd, ADMIN_PASS)
    except Exception:
        return False


def _github_api(url, method="GET", data=None):
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


def _slugify(title):
    slug = re.sub(r"[^a-z0-9\-]+", "", title.lower().replace(" ", "-"))
    return slug.strip("-")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
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

            title = (data.get("title") or "").strip()
            content = (data.get("content") or "").strip()
            excerpt = (data.get("excerpt") or "").strip()
            categories = data.get("categories", [])
            tags = data.get("tags", [])
            image_b64 = data.get("image_base64")
            image_filename = data.get("image_filename")

            if not GITHUB_TOKEN:
                raise ValueError("GITHUB_TOKEN environment variable not set.")
            if not title or not content:
                raise ValueError("Title and content are required.")

            slug = _slugify(title)
            if not slug:
                raise ValueError("Could not generate a valid slug from the title.")

            now = datetime.datetime.now()
            date_str = now.strftime("%Y-%m-%d %H:%M:%S")
            upload_subdir = now.strftime("%Y/%m")

            thumbnail_path = None

            if image_b64 and image_filename:
                safe_filename = re.sub(r"[^a-zA-Z0-9.\-_]+", "", image_filename.replace(" ", "_"))
                repo_image_path = f"wp-content/uploads/{upload_subdir}/{safe_filename}"
                image_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_image_path}"
                _github_api(
                    image_url,
                    method="PUT",
                    data={
                        "message": f"Add image for post: {title}",
                        "content": image_b64,
                        "branch": GITHUB_BRANCH,
                    },
                )
                thumbnail_path = f"/wp-content/uploads/{upload_subdir}/{safe_filename}"

            post_record = {
                "title": title,
                "slug": slug,
                "content": content,
                "excerpt": excerpt,
                "date": date_str,
                "categories": categories,
                "tags": tags,
                "thumbnail": thumbnail_path,
            }

            post_json_path = f"posts/{slug}.json"
            post_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{post_json_path}"

            existing_sha = None
            try:
                existing = _github_api(post_url)
                existing_sha = existing.get("sha")
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise

            encoded_post = base64.b64encode(
                json.dumps(post_record, indent=2).encode("utf-8")
            ).decode("utf-8")

            update_data = {
                "message": f"Add blog post: {title}",
                "content": encoded_post,
                "branch": GITHUB_BRANCH,
            }
            if existing_sha:
                update_data["sha"] = existing_sha

            _github_api(post_url, method="PUT", data=update_data)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "slug": slug}).encode("utf-8"))

        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "message": str(e)}).encode("utf-8"))
