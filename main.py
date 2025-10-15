"""Personal portfolio website (Flask + Firestore + GCS).

- Serves static/dynamic pages
- Fetches projects from Firestore
- Renders long descriptions from Markdown (sanitized)
- Serves images from Google Cloud Storage
"""

from datetime import datetime
from flask import Flask, render_template, flash, redirect, url_for, send_from_directory
from forms import ContactForm
from flask_mail import Mail, Message
from dotenv import load_dotenv
import os
import logging
from google.cloud import firestore
import markdown
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_wtf.csrf import CSRFProtect
import bleach

load_dotenv()

app = Flask(__name__)
# Enable CSRF protection for all WTForms-based views
CSRFProtect(app)

# Honor X-Forwarded-* headers when running behind Railway's proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# --- Configuration (env-driven) ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
email_sender = os.environ.get('MAIL_USERNAME')
app.config['MAIL_USERNAME'] = email_sender
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
email_recipient = os.environ.get('EMAIL_RECIPIENT')

# Initialize Mail once (avoid recreating per request)
mail = Mail(app)

# --- Google credentials (Railway: JSON content via env -> temp file) ---
sa_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if sa_json:
    key_path = "/tmp/service_account.json"
    with open(key_path, "w") as f:
        f.write(sa_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path  # path Firestore SDK expects

logging.basicConfig(level=logging.INFO)

# --- Firestore client ---
db = firestore.Client()

def get_gcs_url(filename: str) -> str:
    """Return a public GCS URL for an object filename in the images bucket."""
    bucket_name = "portfolio-website-images"
    return f"https://storage.googleapis.com/{bucket_name}/{filename}"

@app.context_processor
def inject_year():
    """Inject current year into all templates."""
    return {'current_year': datetime.utcnow().year}

# --- Routes ---

@app.route("/")
def index():
    """Landing page."""
    return render_template("index.html")

@app.route("/about")
def about():
    """About page."""
    return render_template("about.html")

@app.route("/contact", methods=['GET', 'POST'])
def contact():
    """Contact form: sends email via Flask-Mail."""
    form = ContactForm()
    if form.validate_on_submit():
        name = form.name.data
        email = form.email.data
        message = form.message.data
        msg = Message(f'New message from {name}', sender=email_sender, recipients=[email_recipient])
        msg.body = f'From: {name} <{email}>\n\n{message}'
        try:
            # use global mail instance
            mail.send(msg)
            flash('Your message has been sent!', 'success')
            logging.info("Email sent successfully")
        except Exception as e:
            flash('There was an error sending your message.', 'danger')
            logging.error(f"Email send failed: {e}")
        return redirect(url_for('contact'))
    return render_template("contact.html", form=form)

@app.route("/projects")
def projects():
    """List portfolio projects from Firestore."""
    try:
        projects_ref = db.collection('portfolio_projects')
        docs = projects_ref.stream()
        projects_data = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            if 'image_url' in data and data['image_url'] and not data['image_url'].startswith('http'):
                data['image_url'] = get_gcs_url(data['image_url'])
            projects_data.append(data)
    except Exception as e:
        # User-friendly feedback + server log
        flash('Could not load projects at this time.', 'danger')
        logging.error(f"Firestore error: {e}")
        projects_data = []
    return render_template("projects.html", projects=projects_data)

@app.route("/projects/<project_id>")
def project_detail(project_id):
    """Project details: fetch, render Markdown, sanitize, and display."""
    try:
        project_ref = db.collection('portfolio_projects').document(project_id)
        snap = project_ref.get()
        if not snap.exists:
            flash('Project not found.', 'warning')
            return redirect(url_for('projects'))
        project_data = snap.to_dict()
        long_md = project_data.get('long_description_md', '')
        raw_html = markdown.markdown(
            long_md,
            extensions=['extra', 'tables', 'fenced_code', 'codehilite', 'sane_lists']
        )
        # Sanitize rendered HTML to prevent XSS if Markdown contained raw HTML
        allowed_tags = list(bleach.sanitizer.ALLOWED_TAGS) + [
            'p','pre','code','blockquote','hr',
            'h1','h2','h3','h4','h5','h6',
            'table','thead','tbody','tr','th','td',
            'ul','ol','li','strong','em','a'
        ]
        allowed_attrs = {'a': ['href','title','rel','target']}
        clean_html = bleach.clean(raw_html, tags=allowed_tags, attributes=allowed_attrs, strip=True)
        clean_html = bleach.linkify(clean_html)
        project_data['long_description_html'] = clean_html

        if 'image_url' in project_data and project_data['image_url'] and not project_data['image_url'].startswith('http'):
            project_data['image_url'] = get_gcs_url(project_data['image_url'])
    except Exception as e:
        flash('Could not load the project at this time.', 'danger')
        logging.error(f"Firestore error: {e}")
        return redirect(url_for('projects'))
    return render_template("project_detail.html", project=project_data)

@app.route("/robots.txt")
def robots():
    """Serve robots.txt (indexing policy)."""
    return send_from_directory(".", "robots.txt", mimetype="text/plain")

@app.after_request
def secure_headers(resp):
    """Set basic security headers + relaxed CSP to allow CDN and GCS images."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

    # Allow self + jsDelivr CDNs; images from GCS; inline styles (for small inline style attrs)
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' https://storage.googleapis.com data:; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net data:;"
    )
    return resp

# --- Error handlers & health check ---

@app.errorhandler(404)
def not_found(e):
    """404 page."""
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    """500 page."""
    return render_template("500.html"), 500

@app.route("/healthz")
def healthz():
    """Lightweight health check for uptime monitoring."""
    return "ok", 200

# --- Local dev entrypoint (Gunicorn used in production) ---
debug = os.environ.get("FLASK_DEBUG", "0") == "1"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug)