import sqlite3
import os
import re
import glob
import datetime

# Paths
db_path = "/Users/arjungupta/.gemini/antigravity-ide/brain/06024764-27c8-47f9-83ce-3f38b4c267d4/scratch/backup.db"
output_dir = "/Users/arjungupta/Downloads/TUJ_Backup/public"

# Connect to DB
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Helper to rewrite URLs
def rewrite_urls(content):
    if not content:
        return ""
    content = content.replace("https://the-urban-journal.com/", "/")
    content = content.replace("https://the-urban-journal.com", "/")
    return content

# Fetch active terms (categories and tags)
cursor.execute("""
    SELECT t.term_id, t.name, t.slug, tt.taxonomy
    FROM wp_terms t
    JOIN wp_term_taxonomy tt ON t.term_id = tt.term_id
""")
terms = {row[0]: {"name": row[1], "slug": row[2], "taxonomy": row[3]} for row in cursor.fetchall()}

# Fetch post-term relationships
cursor.execute("""
    SELECT object_id, term_taxonomy_id FROM wp_term_relationships
""")
relationships = cursor.fetchall()
post_terms = {}
for pid, term_tax_id in relationships:
    if term_tax_id in terms:
        tinfo = terms[term_tax_id]
        if pid not in post_terms:
            post_terms[pid] = []
        post_terms[pid].append(tinfo)

# Fetch featured images
cursor.execute("""
    SELECT p.ID, pm_file.meta_value
    FROM wp_posts p
    LEFT JOIN wp_postmeta pm_thumb ON p.ID = pm_thumb.post_id AND pm_thumb.meta_key = '_thumbnail_id'
    LEFT JOIN wp_postmeta pm_file ON pm_thumb.meta_value = pm_file.post_id AND pm_file.meta_key = '_wp_attached_file'
    WHERE p.post_type = 'post' AND p.post_status = 'publish'
""")
post_thumbs = {}
for row in cursor.fetchall():
    pid, attached_file = row
    if attached_file:
        post_thumbs[pid] = f"/wp-content/uploads/{attached_file}"
    else:
        post_thumbs[pid] = None

# Fetch all published posts
cursor.execute("""
    SELECT ID, post_title, post_name, post_content, post_date, post_excerpt
    FROM wp_posts
    WHERE post_type = 'post' AND post_status = 'publish'
    ORDER BY post_date DESC
""")
posts = []
for row in cursor.fetchall():
    pid, title, slug, content, date, excerpt = row
    p_categories = [t for t in post_terms.get(pid, []) if t["taxonomy"] == "category"]
    p_tags = [t for t in post_terms.get(pid, []) if t["taxonomy"] == "post_tag"]
    
    posts.append({
        "id": pid,
        "title": title,
        "slug": slug,
        "content": rewrite_urls(content),
        "date": date,
        "excerpt": excerpt,
        "categories": p_categories,
        "tags": p_tags,
        "thumbnail": post_thumbs.get(pid)
    })

# Fetch recent comments
cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='wp_comments'")
has_comments_table = cursor.fetchone()[0] > 0
recent_comments = []
if has_comments_table:
    cursor.execute("""
        SELECT comment_author, comment_post_ID, comment_content, comment_date
        FROM wp_comments
        WHERE comment_approved = '1'
        ORDER BY comment_date DESC
        LIMIT 5
    """)
    for row in cursor.fetchall():
        recent_comments.append({
            "author": row[0],
            "post_id": row[1],
            "content": row[2][:50],
            "date": row[3]
        })

# Unique Taxonomies for linking
unique_categories = {}
unique_tags = {}
unique_months = {}

for post in posts:
    for cat in post["categories"]:
        unique_categories[cat["slug"]] = cat["name"]
    for tag in post["tags"]:
        unique_tags[tag["slug"]] = tag["name"]
        
    dt = datetime.datetime.strptime(post["date"], "%Y-%m-%d %H:%M:%S")
    month_slug = dt.strftime("%Y/%m")
    month_name = dt.strftime("%B %Y")
    unique_months[month_slug] = month_name

# Helper to find Spectra CSS
def get_spectra_css_link(post_id, prefix):
    pattern = f"wp-content/uploads/uag-plugin/assets/*/uag-css-{post_id}.css"
    files = glob.glob(os.path.join(output_dir, pattern))
    if files:
        rel_path = os.path.relpath(files[0], output_dir)
        return f'<link rel="stylesheet" href="{prefix}{rel_path}">'
    return ""

# Helper to find Elementor CSS
def get_elementor_css_link(post_id, prefix):
    path = f"wp-content/uploads/elementor/css/post-{post_id}.css"
    if os.path.exists(os.path.join(output_dir, path)):
        return f'<link rel="stylesheet" href="{prefix}{path}">'
    return ""

# Global Navigation Links
nav_menu = [
    {"title": "Home", "url": "/"},
    {"title": "About", "url": "/about/"},
    {"title": "Blogs", "url": "/https-the-urban-journal-com-latest-blogs/"},
    {"title": "Events", "url": "/events/"}
]

# Generate Header HTML
def get_header_html(page_title, prefix, post_id=None, is_post=False, description=None, canonical_path=None):
    css_links = []
    if post_id:
        spectra_css = get_spectra_css_link(post_id, prefix)
        if spectra_css: css_links.append(spectra_css)
        elementor_css = get_elementor_css_link(post_id, prefix)
        if elementor_css: css_links.append(elementor_css)

    css_links_str = "\n\t".join(css_links)

    menu_items_html = ""
    side_menu_html = ""
    for item in nav_menu:
        active_class = "current-menu-item" if (item["url"] == "/" and page_title == "Home") or (item["url"] != "/" and item["url"].strip("/") in page_title.lower()) else ""
        
        # Make menu link relative
        rel_url = ""
        if item["url"] == "/":
            rel_url = "index.html" if prefix == "" else f"{prefix}index.html"
        else:
            rel_url = f"{prefix}{item['url'].strip('/')}/index.html"
            
        menu_items_html += f'<li class="menu-item {active_class}"><a href="{rel_url}">{item["title"]}</a></li>'
        side_menu_html += f'<a href="{rel_url}">{item["title"]}</a>'

    meta_tags = []
    if description:
        clean_desc = description.replace('"', '&quot;').replace('\n', ' ').strip()
        meta_tags.append(f'<meta name="description" content="{clean_desc}">')
        
    meta_tags.append('<meta name="robots" content="index, follow">')
    
    if canonical_path is not None:
        meta_tags.append(f'<link rel="canonical" href="https://the-urban-journal.com/{canonical_path}">')
    else:
        if page_title == "Home":
            meta_tags.append('<link rel="canonical" href="https://the-urban-journal.com/">')

    meta_tags_str = "\n\t".join(meta_tags)

    header = f"""<!doctype html>
<html lang="en-US">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<title>{page_title} - The Urban Journal</title>
	{meta_tags_str}
	
	<!-- Google Fonts -->
	<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,700;1,400&family=Averia+Serif+Libre:ital,wght@0,300;0,400;0,700;1,400&family=DM+Serif+Display:ital@0;1&family=Roboto:ital,wght@0,300;0,400;0,700;1,400&family=DM+Serif+Text:ital@0;1&family=Roboto+Slab:wght@300;400;700&family=Roboto+Mono:ital,wght@0,300;0,400;0,700;1,400&family=Averia+Sans+Libre:ital,wght@0,300;0,400;0,700;1,400&display=swap" rel="stylesheet">
	
	<!-- WordPress & Theme Core Stylesheets -->
	<link rel="stylesheet" href="{prefix}wp-includes/css/dist/block-library/style.min.css">
	<link rel="stylesheet" href="{prefix}wp-content/plugins/ultimate-addons-for-gutenberg/dist/blocks.css">
	<link rel="stylesheet" href="{prefix}wp-content/themes/personalblogily/style.css">
	<link rel="stylesheet" href="{prefix}wp-content/themes/simply-personal-blog/style.css">
	
	<!-- Page/Post Specific Stylesheets -->
	{css_links_str}
	
	<!-- Responsive Mobile Styling & Pure CSS Mobile Menu -->
	<style>
		/* Floating Side Navigation on Desktop */
		@media (min-width: 1200px) {{
			.side-nav {{
				position: fixed;
				left: 40px;
				top: 50%;
				transform: translateY(-50%);
				z-index: 999;
				display: flex;
				flex-direction: column;
				gap: 18px;
				background: #ffffff;
				padding: 22px 16px;
				border-radius: 6px;
				box-shadow: 0 2px 12px rgba(0,0,0,0.06);
				border: 1px solid #e0e0e0;
				transition: all 0.3s ease;
				
				/* Default state for older/unsupported browsers (always visible) */
				opacity: 1;
				visibility: visible;
			}}
			
			/* Dynamic scroll-driven animation for modern browsers */
			@supports (animation-timeline: scroll()) {{
				@keyframes show-side-nav {{
					0% {{
						opacity: 0;
						visibility: hidden;
						transform: translateY(-50%) scale(0.95);
					}}
					100% {{
						opacity: 1;
						visibility: visible;
						transform: translateY(-50%) scale(1);
					}}
				}}
				.side-nav {{
					animation: show-side-nav linear both;
					animation-timeline: scroll();
					animation-range: 140px 220px; /* Appears after scrolling past the top nav (140px-220px) */
				}}
			}}

			.side-nav a {{
				font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
				font-size: 12px;
				color: #444;
				text-decoration: none;
				font-weight: 600;
				text-transform: uppercase;
				letter-spacing: 1px;
				transition: color 0.2s ease, transform 0.2s ease;
				display: block;
				text-align: center;
			}}
			.side-nav a:hover {{
				color: #000000;
				transform: scale(1.05);
			}}
		}}
		@media (max-width: 1199px) {{
			.side-nav {{
				display: none !important;
			}}
		}}

		/* Image Consistency and Justified Text */
		.uagb-post__image img, 
		.uagb-post__image a img {{
			width: 100% !important;
			height: 240px !important;
			object-fit: cover !important;
		}}
		.uagb-post__excerpt p, 
		.entry-content p {{
			text-align: justify !important;
			text-justify: inter-word;
		}}

		/* Fix for post grid layout */
		.uagb-post-grid.is-grid {{
			display: grid !important;
			grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
			gap: 30px !important;
		}}
		@media (max-width: 976px) {{
			.uagb-post-grid.is-grid {{
				grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
				gap: 20px !important;
			}}
		}}
		@media (max-width: 767px) {{
			.uagb-post-grid.is-grid {{
				grid-template-columns: repeat(1, minmax(0, 1fr)) !important;
				gap: 15px !important;
			}}
		}}

		.header-social-links a:hover {{
			color: #0073aa !important;
			transform: scale(1.1);
		}}
		.footer-social-links a:hover {{
			color: #ffffff !important;
			transform: scale(1.1);
		}}

		@media (max-width: 767px) {{
			.main-navigation {{
				display: block !important;
			}}
			.site-branding {{
				flex-direction: column !important;
				text-align: center !important;
				justify-content: center !important;
				gap: 15px !important;
				padding: 20px 0 !important;
			}}
			.branding-text {{
				text-align: center !important;
			}}
			.site-title {{
				font-size: 28px !important;
			}}
			.site-description {{
				font-size: 13px !important;
			}}
			.header-social-links {{
				justify-content: center !important;
				margin-top: 5px !important;
			}}
			
			/* Mobile Menu Toggle */
			.menu-toggle-label {{
				display: block !important;
				cursor: pointer;
				padding: 12px 0;
				font-size: 16px;
				font-weight: 600;
				text-transform: uppercase;
				border-top: 1px solid #eaeaea;
				border-bottom: 1px solid #eaeaea;
				background-color: #fafafa;
				color: #333;
				letter-spacing: 1px;
			}}
			
			/* Hide desktop menu on mobile by default */
			.center-main-menu {{
				display: none;
				width: 100%;
			}}
			
			/* Show menu when checkbox is checked */
			#menu-toggle-checkbox:checked ~ .center-main-menu {{
				display: block !important;
			}}
			
			/* Stack mobile menu items */
			.pmenu {{
				display: flex !important;
				flex-direction: column !important;
				align-items: center !important;
				padding: 15px 0 !important;
				float: none !important;
				margin: 0 !important;
			}}
			.pmenu li {{
				display: block !important;
				margin: 8px 0 !important;
				float: none !important;
			}}
			.pmenu li a {{
				padding: 8px 20px !important;
				font-size: 15px !important;
			}}
		}}
	</style>
</head>

<body class="{"single-post" if is_post else "page-template-default page"}">

	<div class="side-nav">
		{side_menu_html}
	</div>

	<div id="page" class="site">

		<header id="masthead" class="sheader site-header clearfix">
			<div class="content-wrap">
				<div class="site-branding" style="display: flex; align-items: center; justify-content: space-between; text-align: left; gap: 20px; width: 100%;">
					<div style="display: flex; align-items: center; gap: 20px;">
						<a href="{"index.html" if prefix == "" else f"{prefix}index.html"}" class="branding-logo-link" style="display: inline-block; flex-shrink: 0;">
							<img src="{prefix}wp-content/uploads/2025/07/cropped-cropped-final_logo_TUJ-removebg-preview-300x300.png" alt="The Urban Journal Logo" style="width: 80px; height: 80px; max-height: 80px; object-fit: contain; display: block;" />
						</a>
						<div class="branding-text">
							<p class="site-title" style="font-family: 'Times New Roman', Times, serif; font-size: 36px; margin: 0; font-weight: bold; line-height: 1.2;">
								<a href="{"index.html" if prefix == "" else f"{prefix}index.html"}" rel="home" style="text-decoration: none; color: #000;">The Urban Journal</a>
							</p>
							<p class="site-description" style="margin: 5px 0 0 0; font-size: 15px; color: #666;">Politics, Psyche and Personal Truth</p>
						</div>
					</div>
					<div class="header-social-links" style="display: flex; align-items: center; gap: 20px; flex-shrink: 0;">
						<a href="https://x.com/JournalThe40534" target="_blank" rel="noopener noreferrer" class="social-link-x" title="X (Twitter)" style="color: #444; padding: 6px; text-decoration: none; transition: all 0.2s ease; display: inline-block;">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" style="display: block;"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
						</a>
						<a href="https://www.instagram.com/theurbanjournall?igsh=MXY2ZmZiNmt2ZmNkZQ==" target="_blank" rel="noopener noreferrer" class="social-link-instagram" title="Instagram" style="color: #444; padding: 6px; text-decoration: none; transition: all 0.2s ease; display: inline-block;">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block;"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line></svg>
						</a>
						<a href="https://in.linkedin.com/company/the-urban-journall" target="_blank" rel="noopener noreferrer" class="social-link-linkedin" title="LinkedIn" style="color: #444; padding: 6px; text-decoration: none; transition: all 0.2s ease; display: inline-block;">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block;"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"></path><rect x="2" y="9" width="4" height="12"></rect><circle cx="4" cy="4" r="2"></circle></svg>
						</a>
					</div>
				</div>
			</div>

			<nav id="primary-site-navigation" class="primary-menu main-navigation clearfix">
				<div class="content-wrap text-center">
					<input type="checkbox" id="menu-toggle-checkbox" style="display: none;">
					<label for="menu-toggle-checkbox" class="menu-toggle-label" style="display: none;">
						<span>☰ Menu</span>
					</label>
					
					<div class="center-main-menu">
						<ul id="primary-menu" class="pmenu">
							{menu_items_html}
						</ul>
					</div>
				</div>
			</nav>
		</header>

		<div id="content" class="site-content clearfix">
			<div class="content-wrap">
"""
    return header

# Generate Footer HTML
def get_footer_html(prefix):
    categories_html = ""
    for slug, name in unique_categories.items():
        categories_html += f'<li class="cat-item"><a href="{prefix}category/{slug}/index.html">{name}</a></li>'

    footer = f"""
			</div>
		</div><!-- #content -->

		<footer id="colophon" class="site-footer clearfix">
			<div class="content-wrap">
				<div class="footer-column-wrapper">
					<div class="footer-column-three footer-column-left">
						<div class="widget widget_media_image">
							<a href="{"index.html" if prefix == "" else f"{prefix}index.html"}">
								<img src="{prefix}wp-content/uploads/2025/07/cropped-cropped-final_logo_TUJ-removebg-preview-300x300.png" alt="logo of the urban journal" width="136" height="136" class="image wp-image-2526 attachment-full size-full" style="max-width: 100%; height: auto;" />
							</a>
						</div>
						<div class="widget widget_block">
							<p><strong><a href="{"index.html" if prefix == "" else f"{prefix}index.html"}" style="color: inherit;">The Urban Journal</a></strong> is your space for bold perspectives on politics, deep dives into human psychology, and raw reflections on personal truth. Thought-provoking blogs that question, connect, and challenge.</p>
						</div>
						<div class="widget widget_block" style="margin-top: 15px;">
							<div class="footer-social-links" style="display: flex; align-items: center; gap: 20px; margin-top: 10px;">
								<a href="https://x.com/JournalThe40534" target="_blank" rel="noopener noreferrer" class="social-link-x" title="X (Twitter)" style="color: #bbb; padding: 6px; text-decoration: none; transition: all 0.2s ease; display: inline-block;">
									<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" style="display: block;"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
								</a>
								<a href="https://www.instagram.com/theurbanjournall?igsh=MXY2ZmZiNmt2ZmNkZQ==" target="_blank" rel="noopener noreferrer" class="social-link-instagram" title="Instagram" style="color: #bbb; padding: 6px; text-decoration: none; transition: all 0.2s ease; display: inline-block;">
									<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block;"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line></svg>
								</a>
								<a href="https://in.linkedin.com/company/the-urban-journall" target="_blank" rel="noopener noreferrer" class="social-link-linkedin" title="LinkedIn" style="color: #bbb; padding: 6px; text-decoration: none; transition: all 0.2s ease; display: inline-block;">
									<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block;"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"></path><rect x="2" y="9" width="4" height="12"></rect><circle cx="4" cy="4" r="2"></circle></svg>
								</a>
							</div>
						</div>
					</div>
					
					<div class="footer-column-three footer-column-middle">
						<div class="widget widget_categories">
							<h2 class="widgettitle">Categories</h2>
							<ul>
								{categories_html}
							</ul>
						</div>
					</div>
					
					<div class="footer-column-three footer-column-right">
						<!-- Empty Column -->
					</div>
				</div>
			</div>
		</footer>
	</div><!-- #page -->
</body>
</html>
"""
    return footer

# Generate Sidebar HTML
def get_sidebar_html(prefix):
    recent_posts_html = ""
    for post in posts[:5]:
        recent_posts_html += f'<li><a href="{prefix}{post["slug"]}/index.html">{post["title"]}</a></li>'

    recent_comments_html = ""
    if recent_comments:
        for comment in recent_comments:
            p_slug = ""
            for p in posts:
                if p["id"] == comment["post_id"]:
                    p_slug = p["slug"]
                    break
            recent_comments_html += f'<li class="recentcomments"><span class="comment-author-link">{comment["author"]}</span> on <a href="{prefix}{p_slug}/index.html">{comment["content"]}...</a></li>'
    else:
        recent_comments_html = "<li>No comments yet</li>"
        
    archives_html = ""
    for slug, label in sorted(unique_months.items(), reverse=True):
        archives_html += f'<li><a href="{prefix}date/{slug}/index.html">{label}</a></li>'

    categories_html = ""
    for slug, name in unique_categories.items():
        categories_html += f'<li class="cat-item"><a href="{prefix}category/{slug}/index.html">{name}</a></li>'

    sidebar = f"""
<aside id="secondary" class="featured-sidebar widget-area">
	<div class="widget widget_search">
		<form role="search" method="get" class="search-form" action="#">
			<label>
				<span class="screen-reader-text">Search for:</span>
				<input type="search" class="search-field" placeholder="Search &hellip;" value="" name="s" />
			</label>
			<input type="submit" class="search-submit" value="Search" />
		</form>
	</div>
	
	<div class="widget widget_recent_entries">
		<h2 class="widgettitle">Recent Posts</h2>
		<ul>
			{recent_posts_html}
		</ul>
	</div>

	<div class="widget widget_recent_comments">
		<h2 class="widgettitle">Recent Comments</h2>
		<ul id="recentcomments">
			{recent_comments_html}
		</ul>
	</div>

	<div class="widget widget_archive">
		<h2 class="widgettitle">Archives</h2>
		<ul>
			{archives_html}
		</ul>
	</div>

	<div class="widget widget_categories">
		<h2 class="widgettitle">Categories</h2>
		<ul>
			{categories_html}
		</ul>
	</div>
</aside>
"""
    return sidebar

# Helper to render the Spectra Post Grid
def render_post_grid(prefix, num_posts=3):
    grid_posts = posts[:num_posts]
    grid_html = '<div class="uagb-post-grid uagb-post__items uagb-post__columns-3 is-grid uagb-post__image-position-top">'
    
    for p in grid_posts:
        dt = datetime.datetime.strptime(p["date"], "%Y-%m-%d %H:%M:%S")
        formatted_date = dt.strftime("%B %d, %Y")
        
        thumbnail_html = ""
        if p["thumbnail"]:
            thumbnail_html = f"""
            <div class="uagb-post__image">
                <a href="{prefix}{p["slug"]}/index.html" class="uagb-image-ratio-2-3">
                    <img src="{prefix}{p["thumbnail"].lstrip('/')}" alt="{p["title"]}" loading="lazy" />
                </a>
            </div>
            """
            
        excerpt_text = p["excerpt"] if p["excerpt"] else p["content"][:180].replace('<p>', '').replace('</p>', '') + "..."
        
        grid_html += f"""
        <article class="post-{p["id"]} post type-post status-publish format-standard hentry">
            <div class="uagb-post__inner-wrap">
                {thumbnail_html}
                <div class="uagb-post__text">
                    <h3 class="uagb-post__title">
                        <a href="{prefix}{p["slug"]}/index.html">{p["title"]}</a>
                    </h3>
                    <div class="uagb-post-grid-byline">
                        <span class="uagb-post__author">by <a href="{prefix}about/index.html">Shivani</a></span>
                        <span class="uagb-post__date">· {formatted_date}</span>
                    </div>
                    <div class="uagb-post__excerpt">
                        <p>{excerpt_text}</p>
                    </div>
                    <div class="uagb-post__cta">
                        <a class="uagb-post__cta-link" href="{prefix}{p["slug"]}/index.html">Read More</a>
                    </div>
                </div>
            </div>
        </article>
        """
    grid_html += '</div>'
    return grid_html

# Helper to make content HTML links relative
def make_content_links_relative(html_content, prefix):
    if not html_content:
        return ""
    # Assets
    html_content = html_content.replace('href="/wp-content/', f'href="{prefix}wp-content/')
    html_content = html_content.replace('src="/wp-content/', f'src="{prefix}wp-content/')
    html_content = html_content.replace('href="/wp-includes/', f'href="{prefix}wp-includes/')
    html_content = html_content.replace('src="/wp-includes/', f'src="{prefix}wp-includes/')
    
    # Core Pages
    html_content = html_content.replace('href="/about/"', f'href="{prefix}about/index.html"')
    html_content = html_content.replace('href="/events/"', f'href="{prefix}events/index.html"')
    html_content = html_content.replace('href="/https-the-urban-journal-com-latest-blogs/"', f'href="{prefix}https-the-urban-journal-com-latest-blogs/index.html"')
    html_content = html_content.replace('href="/privacy-policy/"', f'href="{prefix}privacy-policy/index.html"')
    
    # Generic replacements
    html_content = html_content.replace('href="/about/', f'href="{prefix}about/index.html"')
    html_content = html_content.replace('href="/events/', f'href="{prefix}events/index.html"')
    html_content = html_content.replace('href="/https-the-urban-journal-com-latest-blogs/', f'href="{prefix}https-the-urban-journal-com-latest-blogs/index.html"')
    html_content = html_content.replace('href="/privacy-policy/', f'href="{prefix}privacy-policy/index.html"')
    
    # Posts
    for post in posts:
        html_content = html_content.replace(f'href="/{post["slug"]}/"', f'href="{prefix}{post["slug"]}/index.html"')
        html_content = html_content.replace(f'href="/{post["slug"]}/', f'href="{prefix}{post["slug"]}/index.html"')
        
    # Categories
    for cat_slug in unique_categories.keys():
        html_content = html_content.replace(f'href="/category/{cat_slug}/"', f'href="{prefix}category/{cat_slug}/index.html"')
        html_content = html_content.replace(f'href="/category/{cat_slug}/', f'href="{prefix}category/{cat_slug}/index.html"')
        
    # Tags
    for tag_slug in unique_tags.keys():
        html_content = html_content.replace(f'href="/tag/{tag_slug}/"', f'href="{prefix}tag/{tag_slug}/index.html"')
        html_content = html_content.replace(f'href="/tag/{tag_slug}/', f'href="{prefix}tag/{tag_slug}/index.html"')
        
    # Archives
    for month_slug in unique_months.keys():
        html_content = html_content.replace(f'href="/date/{month_slug}/"', f'href="{prefix}date/{month_slug}/index.html"')
        html_content = html_content.replace(f'href="/date/{month_slug}/', f'href="{prefix}date/{month_slug}/index.html"')
        
    return html_content

# Generate Pages
cursor.execute("""
    SELECT ID, post_title, post_name, post_content
    FROM wp_posts
    WHERE post_type = 'page' AND post_status = 'publish'
""")
pages = cursor.fetchall()

for pid, title, slug, content in pages:
    content_rewritten = rewrite_urls(content)
    
    if pid == 1718:
        prefix = ""
        post_grid_pattern = r"<!-- wp:uagb/post-grid .*? /-->"
        post_grid_html = render_post_grid(prefix, 3)
        content_rewritten = re.sub(post_grid_pattern, post_grid_html, content_rewritten)
        
        # Remove unnecessary placeholder content after the blog library link
        marker = "Discover more thought-provoking reads in our"
        idx = content_rewritten.find(marker)
        if idx != -1:
            end_tag = "<!-- /wp:paragraph -->"
            end_idx = content_rewritten.find(end_tag, idx)
            if end_idx != -1:
                content_rewritten = content_rewritten[:end_idx + len(end_tag)]
        
        header_html = get_header_html(title, prefix, post_id=pid, description=None, canonical_path="")
        footer_html = get_footer_html(prefix)
        
        content_rewritten = make_content_links_relative(content_rewritten, prefix)
        page_html = header_html + content_rewritten + footer_html
        file_path = os.path.join(output_dir, "index.html")
    else:
        prefix = "../"
        
        if pid == 2310:
            # Reconstruct the Blog Library page with a beautiful, responsive post grid and proper SEO
            all_posts_grid_html = render_post_grid(prefix, len(posts))
            content_rewritten = f"""
            <header class="page-header text-center" style="margin-bottom: 50px; text-align: center;">
                <h1 class="page-title" style="font-family: 'Times New Roman', Times, serif; font-size: 42px; font-weight: bold; margin-bottom: 15px; color: #111;">The Blog Library</h1>
            </header>

            <div id="primary" class="content-area" style="width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 15px;">
                <main id="main" class="site-main">
                    {all_posts_grid_html}
                </main>
            </div>
            """
            header_html = get_header_html(title, prefix, post_id=pid, description=None, canonical_path="https-the-urban-journal-com-latest-blogs/")
            footer_html = get_footer_html(prefix)
            page_html = header_html + content_rewritten + footer_html
        else:
            header_html = get_header_html(title, prefix, post_id=pid, description=None, canonical_path=f"{slug}/")
            footer_html = get_footer_html(prefix)
            content_rewritten = make_content_links_relative(content_rewritten, prefix)
            page_html = header_html + content_rewritten + footer_html
        
        dir_path = os.path.join(output_dir, slug)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, "index.html")
        
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    print(f"Generated Page: {title} -> {file_path}")

# Generate Blog Posts
for post in posts:
    prefix = "../"
    clean_post_content = re.sub('<[^<]+?>', '', post["content"])
    desc = post["excerpt"] if post["excerpt"] else clean_post_content.strip()[:150] + "..."
    header_html = get_header_html(post["title"], prefix, post_id=post["id"], is_post=True, description=desc, canonical_path=f"{post['slug']}/")
    sidebar_html = get_sidebar_html(prefix)
    footer_html = get_footer_html(prefix)
    
    dt = datetime.datetime.strptime(post["date"], "%Y-%m-%d %H:%M:%S")
    formatted_date = dt.strftime("%B %d, %Y")
    
    cats_list = [f'<a href="{prefix}category/{c["slug"]}/index.html" rel="category tag">{c["name"]}</a>' for c in post["categories"]]
    cats_str = ", ".join(cats_list)
    
    tags_html = ""
    if post["tags"]:
        tags_list = [f'<a href="{prefix}tag/{t["slug"]}/index.html" rel="tag">{t["name"]}</a>' for t in post["tags"]]
        tags_html = '<div class="post-tags">Tags: ' + ", ".join(tags_list) + '</div>'

    post_content_rel = make_content_links_relative(post["content"], prefix)

    # Fetch approved comments for this post
    cursor.execute("""
        SELECT comment_author, comment_content, comment_date
        FROM wp_comments
        WHERE comment_post_ID = ? AND comment_approved = 1
        ORDER BY comment_date ASC
    """, (post["id"],))
    comments = cursor.fetchall()

    comments_html = ""
    if comments:
        comments_html += '<div class="comments-section fbox" style="margin-top: 30px; padding: 25px; background: #fff; border-radius: 4px; border: 1px solid #eee;">'
        comments_html += f'<h3 class="comments-title" style="font-family: \'Times New Roman\', Times, serif; font-weight: bold; margin-bottom: 20px; border-bottom: 2px solid #333; padding-bottom: 10px;">Comments ({len(comments)})</h3>'
        comments_html += '<ul class="comment-list" style="list-style: none; padding: 0; margin: 0;">'
        for author, content_text, c_date in comments:
            c_dt = datetime.datetime.strptime(c_date, "%Y-%m-%d %H:%M:%S") if isinstance(c_date, str) and ' ' in c_date else datetime.datetime.now()
            c_formatted_date = c_dt.strftime("%B %d, %Y at %I:%M %p")
            comments_html += f"""
            <li class="comment-item" style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #f0f0f0;">
                <div class="comment-meta" style="margin-bottom: 8px;">
                    <strong class="comment-author" style="font-size: 16px; color: #111;">{author}</strong>
                    <span class="comment-date" style="font-size: 13px; color: #888; margin-left: 10px;">{c_formatted_date}</span>
                </div>
                <div class="comment-content" style="font-size: 15px; color: #444; line-height: 1.6; text-align: justify;">
                    <p style="margin: 0;">{content_text}</p>
                </div>
            </li>
            """
        comments_html += '</ul></div>'

    comment_form_html = f"""
    <div class="comment-respond fbox" style="margin-top: 30px; padding: 25px; background: #fff; border-radius: 4px; border: 1px solid #eee;">
        <h3 class="comment-reply-title" style="font-family: 'Times New Roman', Times, serif; font-weight: bold; margin-bottom: 20px; border-bottom: 2px solid #333; padding-bottom: 10px;">Leave a Comment</h3>
        <form id="commentform" style="display: flex; flex-direction: column; gap: 15px;">
            <input type="hidden" name="post_id" value="{post["id"]}">
            <div style="display: flex; gap: 15px; flex-wrap: wrap;">
                <div style="flex: 1; min-width: 250px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 5px; font-size: 14px;">Name *</label>
                    <input type="text" name="author" required style="width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 15px;">
                </div>
                <div style="flex: 1; min-width: 250px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 5px; font-size: 14px;">Email (will be verified) *</label>
                    <input type="email" name="email" required style="width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 15px;">
                </div>
            </div>
            <div>
                <label style="display: block; font-weight: 600; margin-bottom: 5px; font-size: 14px;">Comment *</label>
                <textarea name="comment" required rows="6" style="width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 15px; resize: vertical;"></textarea>
            </div>
            <div id="comment-message" style="display: none; padding: 12px; border-radius: 4px; font-size: 15px; font-weight: 500;"></div>
            <div>
                <button type="submit" style="background: #111; color: #fff; border: none; padding: 12px 24px; font-size: 15px; font-weight: bold; border-radius: 4px; cursor: pointer; transition: background 0.2s ease;">Submit Comment</button>
            </div>
        </form>
        <script>
            document.getElementById('commentform').addEventListener('submit', function(e) {{
                e.preventDefault();
                const form = e.target;
                const button = form.querySelector('button[type="submit"]');
                const msgDiv = document.getElementById('comment-message');
                
                button.disabled = true;
                button.textContent = 'Sending verification...';
                msgDiv.style.display = 'none';
                
                const data = {{
                    post_id: form.post_id.value,
                    author: form.author.value,
                    email: form.email.value,
                    comment: form.comment.value
                }};
                
                fetch('/api/submit_comment', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(data)
                }})
                .then(res => res.json())
                .then(res => {{
                    if (res.success) {{
                        msgDiv.style.backgroundColor = '#d4edda';
                        msgDiv.style.color = '#155724';
                        msgDiv.style.border = '1px solid #c3e6cb';
                        msgDiv.textContent = 'A verification email has been sent. Please check your inbox and click the link to verify your comment.';
                        msgDiv.style.display = 'block';
                        form.reset();
                    }} else {{
                        throw new Error(res.message || 'Failed to submit comment.');
                    }}
                }})
                .catch(err => {{
                    msgDiv.style.backgroundColor = '#f8d7da';
                    msgDiv.style.color = '#721c24';
                    msgDiv.style.border = '1px solid #f5c6cb';
                    msgDiv.textContent = err.message;
                    msgDiv.style.display = 'block';
                }})
                .finally(() => {{
                    button.disabled = false;
                    button.textContent = 'Submit Comment';
                }});
            }});
        </script>
    </div>
    """

    post_body = f"""
<div id="primary" class="featured-content content-area">
	<main id="main" class="site-main">
		<article id="post-{post["id"]}" class="post-{post["id"]} post type-post status-publish format-standard hentry category-politics posts-entry fbox">
			<header class="entry-header">
				<h1 class="entry-title">{post["title"]}</h1>
				<div class="entry-meta">
					<div class="blog-data-wrapper">
						<div class="post-data-divider"></div>
						<div class="post-data-positioning">
							<div class="post-data-text">
								<span class="posted-on">Posted on <a href="{prefix}{post["slug"]}/index.html" rel="bookmark"><time class="entry-date published" datetime="{post["date"]}">{formatted_date}</time></a></span>
								<span class="byline"> by <span class="author vcard"><a class="url fn n" href="{prefix}about/index.html">Shivani</a></span></span>
								<span class="cat-links"> in {cats_str}</span>
							</div>
						</div>
					</div>
				</div>
			</header>
			
			<div class="entry-content">
				{post_content_rel}
				{tags_html}
			</div>
		</article>
		{comments_html}
		{comment_form_html}
	</main>
</div>
"""
    
    page_html = header_html + post_body + sidebar_html + footer_html
    
    dir_path = os.path.join(output_dir, post["slug"])
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, "index.html")
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    print(f"Generated Post: {post['title']} -> {file_path}")

# Generate Category Pages
for slug, cat_name in unique_categories.items():
    prefix = "../../"
    desc = f"Browse all articles in the {cat_name} category on The Urban Journal."
    header_html = get_header_html(f"Category: {cat_name}", prefix, description=desc, canonical_path=f"category/{slug}/")
    sidebar_html = get_sidebar_html(prefix)
    footer_html = get_footer_html(prefix)
    
    # Filter posts
    cat_posts = [p for p in posts if slug in [c["slug"] for c in p["categories"]]]
    
    posts_list_html = f'<h1 class="page-title">Category: {cat_name}</h1>'
    for p in cat_posts:
        dt = datetime.datetime.strptime(p["date"], "%Y-%m-%d %H:%M:%S")
        formatted_date = dt.strftime("%B %d, %Y")
        
        posts_list_html += f"""
<article class="posts-entry fbox">
	<header class="entry-header">
		<h2 class="entry-title"><a href="{prefix}{p["slug"]}/index.html" rel="bookmark">{p["title"]}</a></h2>
		<div class="entry-meta">
			<div class="blog-data-wrapper">
				<div class="post-data-divider"></div>
				<div class="post-data-positioning">
					<div class="post-data-text">
						<span class="posted-on">Posted on <time class="entry-date published">{formatted_date}</time></span>
					</div>
				</div>
			</div>
		</div>
	</header>
	<div class="entry-content">
		<p>{p["excerpt"] if p["excerpt"] else p["content"][:300].replace('<p>', '').replace('</p>', '') + "..."}</p>
		<a class="more-link" href="{prefix}{p["slug"]}/index.html">Read More</a>
	</div>
</article>
"""

    body_html = f"""
<div id="primary" class="featured-content content-area">
	<main id="main" class="site-main">
		{posts_list_html}
	</main>
</div>
"""
    page_html = header_html + body_html + sidebar_html + footer_html
    
    dir_path = os.path.join(output_dir, "category", slug)
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, "index.html")
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    print(f"Generated Category Page: {cat_name} -> {file_path}")

# Generate Tag Pages
for slug, tag_name in unique_tags.items():
    prefix = "../../"
    desc = f"Browse all articles tagged with #{tag_name} on The Urban Journal."
    header_html = get_header_html(f"Tag: {tag_name}", prefix, description=desc, canonical_path=f"tag/{slug}/")
    sidebar_html = get_sidebar_html(prefix)
    footer_html = get_footer_html(prefix)
    
    tag_posts = [p for p in posts if slug in [t["slug"] for t in p["tags"]]]
    
    posts_list_html = f'<h1 class="page-title">Tag: {tag_name}</h1>'
    for p in tag_posts:
        dt = datetime.datetime.strptime(p["date"], "%Y-%m-%d %H:%M:%S")
        formatted_date = dt.strftime("%B %d, %Y")
        
        posts_list_html += f"""
<article class="posts-entry fbox">
	<header class="entry-header">
		<h2 class="entry-title"><a href="{prefix}{p["slug"]}/index.html" rel="bookmark">{p["title"]}</a></h2>
		<div class="entry-meta">
			<div class="blog-data-wrapper">
				<div class="post-data-divider"></div>
				<div class="post-data-positioning">
					<div class="post-data-text">
						<span class="posted-on">Posted on <time class="entry-date published">{formatted_date}</time></span>
					</div>
				</div>
			</div>
		</div>
	</header>
	<div class="entry-content">
		<p>{p["excerpt"] if p["excerpt"] else p["content"][:300].replace('<p>', '').replace('</p>', '') + "..."}</p>
		<a class="more-link" href="{prefix}{p["slug"]}/index.html">Read More</a>
	</div>
</article>
"""

    body_html = f"""
<div id="primary" class="featured-content content-area">
	<main id="main" class="site-main">
		{posts_list_html}
	</main>
</div>
"""
    page_html = header_html + body_html + sidebar_html + footer_html
    
    dir_path = os.path.join(output_dir, "tag", slug)
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, "index.html")
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    print(f"Generated Tag Page: {tag_name} -> {file_path}")

# Generate Archive Pages by Date
for month_slug, month_name in unique_months.items():
    prefix = "../../../"
    desc = f"Browse articles published in {month_name} on The Urban Journal."
    header_html = get_header_html(f"Archive: {month_name}", prefix, description=desc, canonical_path=f"date/{month_slug}/")
    sidebar_html = get_sidebar_html(prefix)
    footer_html = get_footer_html(prefix)
    
    archive_posts = []
    for p in posts:
        p_dt = datetime.datetime.strptime(p["date"], "%Y-%m-%d %H:%M:%S")
        if p_dt.strftime("%Y/%m") == month_slug:
            archive_posts.append(p)
            
    posts_list_html = f'<h1 class="page-title">Archive: {month_name}</h1>'
    for p in archive_posts:
        dt = datetime.datetime.strptime(p["date"], "%Y-%m-%d %H:%M:%S")
        formatted_date = dt.strftime("%B %d, %Y")
        
        posts_list_html += f"""
<article class="posts-entry fbox">
	<header class="entry-header">
		<h2 class="entry-title"><a href="{prefix}{p["slug"]}/index.html" rel="bookmark">{p["title"]}</a></h2>
		<div class="entry-meta">
			<div class="blog-data-wrapper">
				<div class="post-data-divider"></div>
				<div class="post-data-positioning">
					<div class="post-data-text">
						<span class="posted-on">Posted on <time class="entry-date published">{formatted_date}</time></span>
					</div>
				</div>
			</div>
		</div>
	</header>
	<div class="entry-content">
		<p>{p["excerpt"] if p["excerpt"] else p["content"][:300].replace('<p>', '').replace('</p>', '') + "..."}</p>
		<a class="more-link" href="{prefix}{p["slug"]}/index.html">Read More</a>
	</div>
</article>
"""

    body_html = f"""
<div id="primary" class="featured-content content-area">
	<main id="main" class="site-main">
		{posts_list_html}
	</main>
</div>
"""
    page_html = header_html + body_html + sidebar_html + footer_html
    
    dir_path = os.path.join(output_dir, "date", month_slug)
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, "index.html")
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    print(f"Generated Archive Page: {month_name} -> {file_path}")

conn.close()
print("All static pages generated successfully with relative links!")
