import os
import re
import sys
import json
import sqlite3
import time
import datetime
import email
import subprocess
import urllib.parse
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.getenv("ADMIN_PORT", "8081"))
DB_PATH = "/Users/arjungupta/.gemini/antigravity-ide/brain/06024764-27c8-47f9-83ce-3f38b4c267d4/scratch/backup.db"
WORKSPACE_DIR = "/Users/arjungupta/Downloads/TUJ_Backup"

# Add api directory to path to import serverless functions for local testing
sys.path.append(os.path.join(WORKSPACE_DIR, "api"))
try:
    import submit_comment
    import verify_comment
except ImportError:
    submit_comment = None
    verify_comment = None

def run_site_generator():
    """Run the build_site.py script to regenerate static HTML pages."""
    try:
        subprocess.run(["python3", "build_site.py"], cwd=WORKSPACE_DIR, check=True)
        return True
    except Exception as e:
        print(f"Error running build_site.py: {e}")
        return False

def push_to_github(commit_message):
    """Commit changes and push to the GitHub repository."""
    try:
        subprocess.run(["git", "add", "."], cwd=WORKSPACE_DIR, check=True)
        subprocess.run(["git", "commit", "-m", commit_message], cwd=WORKSPACE_DIR, check=True)
        subprocess.run(["git", "push"], cwd=WORKSPACE_DIR, check=True)
        return True
    except Exception as e:
        print(f"Error pushing to GitHub: {e}")
        return False

class AdminHTTPRequestHandler(BaseHTTPRequestHandler):
    # Allowed credentials (email:password) encoded in base64 for basic auth
    _allowed_credentials = {
        "shivanip1906@gmail.com": "Shivani@1906",
        "arjunnitin9@gmail.com": "Shivani@1906"
    }

    def _is_authorized(self):
        auth_header = self.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Basic '):
            return False
        encoded = auth_header.split(' ', 1)[1].strip()
        try:
            decoded_bytes = base64.b64decode(encoded)
            decoded = decoded_bytes.decode('utf-8')
            username, password = decoded.split(':', 1)
        except Exception:
            return False
        expected_password = self._allowed_credentials.get(username)
        return expected_password == password

    def _require_auth(self):
        if not self._is_authorized():
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Admin Area"')
            self.end_headers()
            self.wfile.write(b'Authentication required')
            return False
        return True
    def do_GET(self):
        if not self._require_auth():
            return
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self.get_admin_ui_html().encode('utf-8'))
            
        elif parsed_path.path == '/api/data':
            self.handle_get_data()
            
        elif parsed_path.path == '/api/verify_comment' and verify_comment:
            verify_comment.handler(self.request, self.client_address, self.server)
            
        else:
            # Serve static files from workspace
            file_path = os.path.join(WORKSPACE_DIR, parsed_path.path.lstrip('/'))
            if os.path.isdir(file_path):
                file_path = os.path.join(file_path, "index.html")
                
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.send_response(200)
                if file_path.endswith('.html'):
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                elif file_path.endswith('.css'):
                    self.send_header('Content-Type', 'text/css')
                elif file_path.endswith('.js'):
                    self.send_header('Content-Type', 'application/javascript')
                elif file_path.endswith('.png'):
                    self.send_header('Content-Type', 'image/png')
                elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                    self.send_header('Content-Type', 'image/jpeg')
                elif file_path.endswith('.svg'):
                    self.send_header('Content-Type', 'image/svg+xml')
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "File not found")

    def do_POST(self):
        if not self._require_auth():
            return
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/api/comments/approve':
            self.handle_approve_comment()
            
        elif parsed_path.path == '/api/comments/reject':
            self.handle_reject_comment()
            
        elif parsed_path.path == '/api/posts/create':
            self.handle_create_post()
            
        elif parsed_path.path == '/api/submit_comment' and submit_comment:
            submit_comment.handler(self.request, self.client_address, self.server)
            
        else:
            self.send_error(404, "Endpoint not found")

    def handle_get_data(self):
        # 1. Fetch pending comments from local directory
        pending_comments = []
        pending_dir = os.path.join(WORKSPACE_DIR, "pending_comments")
        if os.path.exists(pending_dir):
            for file in os.listdir(pending_dir):
                if file.endswith(".json"):
                    file_path = os.path.join(pending_dir, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            comment_data = json.load(f)
                            comment_data["filename"] = file
                            pending_comments.append(comment_data)
                    except Exception as e:
                        print(f"Error reading pending comment {file}: {e}")

        # 2. Fetch approved comments from SQLite database
        approved_comments = []
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.comment_ID, c.comment_author, c.comment_author_email, c.comment_content, c.comment_date, p.post_title
                FROM wp_comments c
                JOIN wp_posts p ON c.comment_post_ID = p.ID
                WHERE c.comment_approved = 1
                ORDER BY c.comment_date DESC
            """)
            for row in cursor.fetchall():
                approved_comments.append({
                    "id": row[0],
                    "author": row[1],
                    "email": row[2],
                    "comment": row[3],
                    "date": row[4],
                    "post_title": row[5]
                })
            conn.close()
        except Exception as e:
            print(f"Database error: {e}")

        response_data = {
            "pending": pending_comments,
            "approved": approved_comments
        }
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode('utf-8'))

    def handle_approve_comment(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            filename = data.get('filename')
            
            if not filename:
                raise ValueError("Filename is required.")
                
            # Read comment details from pending file
            file_path = os.path.join(WORKSPACE_DIR, "pending_comments", filename)
            if not os.path.exists(file_path):
                raise FileNotFoundError("Pending comment file not found.")
                
            with open(file_path, "r", encoding="utf-8") as f:
                comment_data = json.load(f)
                
            # Save to database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Format date
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute("""
                INSERT INTO wp_comments (comment_post_ID, comment_author, comment_author_email, comment_content, comment_date, comment_approved)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (comment_data['post_id'], comment_data['author'], comment_data['email'], comment_data['comment'], now_str))
            
            conn.commit()
            conn.close()
            
            # Delete pending file
            os.remove(file_path)
            
            # Regenerate website
            run_site_generator()
            
            # Push to GitHub
            push_to_github(f"Approve comment by {comment_data['author']}")
            
            self.send_json_response({"success": True})
            
        except Exception as e:
            self.send_json_response({"success": False, "message": str(e)}, status=400)

    def handle_reject_comment(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            filename = data.get('filename')
            comment_id = data.get('id')
            
            if filename:
                # Rejecting a pending comment
                file_path = os.path.join(WORKSPACE_DIR, "pending_comments", filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                push_to_github("Reject pending comment")
            elif comment_id:
                # Deleting an approved comment
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM wp_comments WHERE comment_ID = ?", (comment_id,))
                conn.commit()
                conn.close()
                
                # Regenerate website
                run_site_generator()
                push_to_github("Delete approved comment")
                
            self.send_json_response({"success": True})
            
        except Exception as e:
            self.send_json_response({"success": False, "message": str(e)}, status=400)

    def handle_create_post(self):
        try:
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                raise ValueError("Content-Type must be multipart/form-data")
                
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            # Parse multipart form data using email parser
            msg = email.message_from_bytes(b"Content-Type: " + content_type.encode('utf-8') + b"\r\n\r\n" + body)
            
            form_fields = {}
            file_data = None
            file_name = None
            
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                
                name = part.get_param('name', header='content-disposition')
                filename = part.get_filename()
                
                if filename:
                    file_data = part.get_payload(decode=True)
                    file_name = filename
                else:
                    form_fields[name] = part.get_payload(decode=True).decode('utf-8').strip()
            
            title = form_fields.get('title')
            content = form_fields.get('content')
            categories_selected = [k for k, v in form_fields.items() if k.startswith('category_')]
            tags_input = form_fields.get('tags', '')
            
            if not title or not content:
                raise ValueError("Title and Content are required.")
                
            # Create slug
            slug = re.sub(r'[^a-z0-9\-]+', '', title.lower().replace(' ', '-'))
            slug = slug.strip('-')
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Save Featured Image if uploaded
            thumbnail_post_id = None
            if file_name and file_data:
                # Create directory path
                upload_dir = os.path.join(WORKSPACE_DIR, "wp-content", "uploads", "2025", "07")
                os.makedirs(upload_dir, exist_ok=True)
                
                # Save file
                safe_file_name = re.sub(r'[^a-zA-Z0-9\.\-_]+', '', file_name.replace(' ', '_'))
                target_file_path = os.path.join(upload_dir, safe_file_name)
                with open(target_file_path, "wb") as f:
                    f.write(file_data)
                    
                relative_path = f"2025/07/{safe_file_name}"
                guid_path = f"/wp-content/uploads/{relative_path}"
                
                # Insert attachment post into wp_posts
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                    INSERT INTO wp_posts (post_author, post_date, post_date_gmt, post_content, post_title, post_excerpt, post_status, comment_status, ping_status, post_name, to_ping, pinged, post_modified, post_modified_gmt, post_content_filtered, post_parent, guid, menu_order, post_type, post_mime_type, comment_count)
                    VALUES (1, ?, ?, '', ?, '', 'inherit', 'closed', 'closed', ?, '', '', ?, ?, '', 0, ?, 0, 'attachment', 'image/jpeg', 0)
                """, (now_str, now_str, safe_file_name, safe_file_name, now_str, now_str, guid_path))
                
                thumbnail_post_id = cursor.lastrowid
                
                # Insert attachment metadata into wp_postmeta
                cursor.execute("""
                    INSERT INTO wp_postmeta (post_id, meta_key, meta_value)
                    VALUES (?, '_wp_attached_file', ?)
                """, (thumbnail_post_id, relative_path))
            
            # Insert Blog Post into wp_posts
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO wp_posts (post_author, post_date, post_date_gmt, post_content, post_title, post_excerpt, post_status, comment_status, ping_status, post_name, to_ping, pinged, post_modified, post_modified_gmt, post_content_filtered, post_parent, guid, menu_order, post_type, post_mime_type, comment_count)
                VALUES (1, ?, ?, ?, ?, '', 'publish', 'open', 'open', ?, '', '', ?, ?, '', 0, '', 0, 'post', '', 0)
            """, (now_str, now_str, content, title, slug, now_str, now_str))
            
            post_id = cursor.lastrowid
            
            # Link Thumbnail to Post
            if thumbnail_post_id:
                cursor.execute("""
                    INSERT INTO wp_postmeta (post_id, meta_key, meta_value)
                    VALUES (?, '_thumbnail_id', ?)
                """, (post_id, str(thumbnail_post_id)))
                
            # Associate Categories in wp_term_relationships
            for cat_field in categories_selected:
                # Extract term_taxonomy_id from the category checkbox name (e.g. category_3 -> 3)
                term_taxonomy_id = int(cat_field.split('_')[1])
                cursor.execute("""
                    INSERT INTO wp_term_relationships (object_id, term_taxonomy_id, term_order)
                    VALUES (?, ?, 0)
                """, (post_id, term_taxonomy_id))
                
            # Parse and Associate Tags
            if tags_input:
                tags = [t.strip() for t in tags_input.split(',') if t.strip()]
                for tag_name in tags:
                    tag_slug = re.sub(r'[^a-z0-9\-]+', '', tag_name.lower().replace(' ', '-')).strip('-')
                    
                    # Check if tag term already exists
                    cursor.execute("SELECT term_id FROM wp_terms WHERE name = ? OR slug = ?", (tag_name, tag_slug))
                    row = cursor.fetchone()
                    if row:
                        term_id = row[0]
                        # Get term_taxonomy_id
                        cursor.execute("SELECT term_taxonomy_id FROM wp_term_taxonomy WHERE term_id = ? AND taxonomy = 'post_tag'", (term_id,))
                        tax_row = cursor.fetchone()
                        if tax_row:
                            term_taxonomy_id = tax_row[0]
                        else:
                            # Create taxonomy entry
                            cursor.execute("INSERT INTO wp_term_taxonomy (term_id, taxonomy, description, parent, count) VALUES (?, 'post_tag', '', 0, 1)", (term_id,))
                            term_taxonomy_id = cursor.lastrowid
                    else:
                        # Insert term
                        cursor.execute("INSERT INTO wp_terms (name, slug, term_group) VALUES (?, ?, 0)", (tag_name, tag_slug))
                        term_id = cursor.lastrowid
                        # Insert taxonomy
                        cursor.execute("INSERT INTO wp_term_taxonomy (term_id, taxonomy, description, parent, count) VALUES (?, 'post_tag', '', 0, 1)", (term_id,))
                        term_taxonomy_id = cursor.lastrowid
                        
                    # Insert relationship
                    cursor.execute("""
                        INSERT INTO wp_term_relationships (object_id, term_taxonomy_id, term_order)
                        VALUES (?, ?, 0)
                    """, (post_id, term_taxonomy_id))
            
            conn.commit()
            conn.close()
            
            # Regenerate website
            run_site_generator()
            
            # Push to GitHub
            push_to_github(f"Publish new blog post: {title}")
            
            # Redirect back to admin panel
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
            
        except Exception as e:
            self.send_json_response({"success": False, "message": str(e)}, status=400)

    def send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def get_admin_ui_html(self):
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Urban Journal - Admin Panel</title>
    <style>
        :root {
            --bg-color: #f7f7f7;
            --card-bg: #ffffff;
            --text-color: #222222;
            --text-muted: #666666;
            --primary: #111111;
            --primary-hover: #333333;
            --accent: #0073aa;
            --border-color: #eaeaea;
            --success: #2e7d32;
            --error: #c62828;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 0;
            line-height: 1.6;
        }
        
        header {
            background-color: var(--card-bg);
            border-bottom: 1px solid var(--border-color);
            padding: 20px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        header h1 {
            font-family: 'Times New Roman', Times, serif;
            font-size: 26px;
            margin: 0;
            font-weight: bold;
        }
        
        .container {
            max-width: 1200px;
            margin: 40px auto;
            padding: 0 20px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
        }
        
        @media (max-width: 900px) {
            .container {
                grid-template-columns: 1fr;
            }
        }
        
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.02);
        }
        
        .card h2 {
            font-family: 'Times New Roman', Times, serif;
            font-size: 22px;
            margin-top: 0;
            margin-bottom: 25px;
            border-bottom: 2px solid var(--primary);
            padding-bottom: 8px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            font-weight: 600;
            margin-bottom: 6px;
            font-size: 14px;
        }
        
        .form-group input[type="text"],
        .form-group input[type="email"],
        .form-group textarea {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 15px;
            box-sizing: border-box;
            background: #fff;
        }
        
        .form-group textarea {
            resize: vertical;
        }
        
        .checkbox-group {
            display: flex;
            gap: 20px;
            margin-top: 5px;
        }
        
        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 500;
            font-size: 15px;
            cursor: pointer;
        }
        
        .btn {
            background-color: var(--primary);
            color: white;
            border: none;
            padding: 12px 24px;
            font-size: 15px;
            font-weight: bold;
            border-radius: 4px;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .btn:hover {
            background-color: var(--primary-hover);
        }
        
        .btn-success {
            background-color: var(--success);
        }
        .btn-success:hover {
            background-color: #1b5e20;
        }
        
        .btn-danger {
            background-color: var(--error);
        }
        .btn-danger:hover {
            background-color: #b71c1c;
        }
        
        .comment-list {
            list-style: none;
            padding: 0;
            margin: 0;
            max-height: 600px;
            overflow-y: auto;
        }
        
        .comment-item {
            padding: 20px;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            margin-bottom: 15px;
            background-color: #fafafa;
        }
        
        .comment-meta {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 14px;
        }
        
        .comment-author {
            font-weight: bold;
        }
        
        .comment-post {
            font-style: italic;
            color: var(--text-muted);
        }
        
        .comment-content {
            margin-top: 10px;
            font-size: 15px;
            color: #333;
            white-space: pre-line;
        }
        
        .comment-actions {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        
        .comment-actions .btn {
            padding: 6px 12px;
            font-size: 13px;
        }
        
        .empty-state {
            text-align: center;
            color: var(--text-muted);
            padding: 40px 20px;
            font-style: italic;
        }
        
        .tabs {
            display: flex;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 20px;
        }
        
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            font-weight: 600;
            font-size: 15px;
        }
        
        .tab.active {
            border-bottom-color: var(--primary);
            color: var(--primary);
        }
    </style>
</head>
<body>
    <header>
        <h1>The Urban Journal — Administration</h1>
        <div style="font-size: 14px; color: var(--text-muted);">Local Moderation Server</div>
    </header>
    
    <div class="container">
        <!-- Add Blog Post Section -->
        <div class="card">
            <h2>Write a New Blog Post</h2>
            <form action="/api/posts/create" method="POST" enctype="multipart/form-data">
                <div class="form-group">
                    <label>Title *</label>
                    <input type="text" name="title" required placeholder="Enter blog title...">
                </div>
                
                <div class="form-group">
                    <label>Categories *</label>
                    <div class="checkbox-group">
                        <label class="checkbox-label">
                            <input type="checkbox" name="category_3" checked> Politics
                        </label>
                        <label class="checkbox-label">
                            <input type="checkbox" name="category_4"> Psychology
                        </label>
                        <label class="checkbox-label">
                            <input type="checkbox" name="category_5"> Personal Truth
                        </label>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Tags (comma-separated)</label>
                    <input type="text" name="tags" placeholder="e.g. Media, Democracy, Society">
                </div>
                
                <div class="form-group">
                    <label>Featured Image *</label>
                    <input type="file" name="image" accept="image/*" required>
                </div>
                
                <div class="form-group">
                    <label>Content (HTML/Text) *</label>
                    <textarea name="content" required rows="14" placeholder="Write your blog post content here..."></textarea>
                </div>
                
                <div style="text-align: right;">
                    <button type="submit" class="btn">Publish Post</button>
                </div>
            </form>
        </div>
        
        <!-- Comment Moderation Section -->
        <div class="card">
            <h2>Moderate Comments</h2>
            
            <div class="tabs">
                <div id="tab-pending" class="tab active" onclick="switchTab('pending')">Pending Approval</div>
                <div id="tab-approved" class="tab" onclick="switchTab('approved')">Approved</div>
            </div>
            
            <div id="pending-container">
                <ul id="pending-list" class="comment-list">
                    <!-- Dynamic pending comments -->
                </ul>
            </div>
            
            <div id="approved-container" style="display: none;">
                <ul id="approved-list" class="comment-list">
                    <!-- Dynamic approved comments -->
                </ul>
            </div>
        </div>
    </div>
    
    <script>
        let commentData = { pending: [], approved: [] };
        
        function fetchComments() {
            fetch('/api/data')
                .then(res => res.json())
                .then(data => {
                    commentData = data;
                    renderComments();
                })
                .catch(err => console.error("Error fetching data:", err));
        }
        
        function renderComments() {
            const pendingList = document.getElementById('pending-list');
            const approvedList = document.getElementById('approved-list');
            
            // Render Pending
            if (commentData.pending.length === 0) {
                pendingList.innerHTML = '<li class="empty-state">No comments pending moderation.</li>';
            } else {
                pendingList.innerHTML = commentData.pending.map(c => `
                    <li class="comment-item">
                        <div class="comment-meta">
                            <span class="comment-author">${c.author} (${c.email})</span>
                            <span class="comment-post">on Post ID: ${c.post_id}</span>
                        </div>
                        <div class="comment-content">${c.comment}</div>
                        <div class="comment-actions">
                            <button class="btn btn-success" onclick="approveComment('${c.filename}')">Approve</button>
                            <button class="btn btn-danger" onclick="rejectComment('${c.filename}', null)">Reject</button>
                        </div>
                    </li>
                `).join('');
            }
            
            // Render Approved
            if (commentData.approved.length === 0) {
                approvedList.innerHTML = '<li class="empty-state">No approved comments.</li>';
            } else {
                approvedList.innerHTML = commentData.approved.map(c => `
                    <li class="comment-item">
                        <div class="comment-meta">
                            <span class="comment-author">${c.author} (${c.email})</span>
                            <span class="comment-post">on "${c.post_title}"</span>
                        </div>
                        <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 8px;">Published: ${c.date}</div>
                        <div class="comment-content">${c.comment}</div>
                        <div class="comment-actions">
                            <button class="btn btn-danger" onclick="rejectComment(null, ${c.id})">Delete</button>
                        </div>
                    </li>
                `).join('');
            }
        }
        
        function switchTab(type) {
            document.getElementById('tab-pending').classList.toggle('active', type === 'pending');
            document.getElementById('tab-approved').classList.toggle('active', type === 'approved');
            
            document.getElementById('pending-container').style.display = type === 'pending' ? 'block' : 'none';
            document.getElementById('approved-container').style.display = type === 'approved' ? 'block' : 'none';
        }
        
        function approveComment(filename) {
            if (!confirm("Are you sure you want to approve this comment? This will regenerate the site and push to GitHub.")) return;
            
            fetch('/api/comments/approve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename })
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert("Comment approved successfully!");
                    fetchComments();
                } else {
                    alert("Error: " + res.message);
                }
            });
        }
        
        function rejectComment(filename, id) {
            const msg = filename ? "Are you sure you want to reject this pending comment?" : "Are you sure you want to delete this approved comment? This will regenerate the site.";
            if (!confirm(msg)) return;
            
            fetch('/api/comments/reject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename, id })
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert("Comment deleted successfully!");
                    fetchComments();
                } else {
                    alert("Error: " + res.message);
                }
            });
        }
        
        // Initial Fetch
        fetchComments();
    </script>
</body>
</html>
"""

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, AdminHTTPRequestHandler)
    print(f"Admin Dashboard running locally at http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down admin server...")
        sys.exit(0)

if __name__ == '__main__':
    run_server()
