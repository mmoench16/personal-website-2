from datetime import datetime
from flask import Flask, render_template, flash, redirect, url_for, send_from_directory
from forms import ContactForm
from flask_mail import Mail, Message
from dotenv import load_dotenv
import os
import logging
from google.cloud import firestore
from google.cloud import storage
import markdown  # Add this import at the top

load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
email_sender = os.environ.get('MAIL_USERNAME')
app.config['MAIL_USERNAME'] = email_sender
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
email_recipient = os.environ.get('EMAIL_RECIPIENT')
load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

mail = Mail(app)

# Configure logging (at the top of your file, after imports)
logging.basicConfig(level=logging.INFO)

# Initialize Firestore client (make sure GOOGLE_APPLICATION_CREDENTIALS is set)
db = firestore.Client()

# Helper function to get GCS URL
def get_gcs_url(filename):
    """Convert filename to full GCS URL"""
    bucket_name = "portfolio-website-images" 
    return f"https://storage.googleapis.com/{bucket_name}/{filename}"

@app.context_processor
def inject_year():
    return {'current_year': datetime.utcnow().year}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact", methods=['GET', 'POST'])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        name = form.name.data
        email = form.email.data
        message = form.message.data

        msg = Message(f'New message from {name}', sender=email_sender, recipients=[email_recipient])
        msg.body = f'From: {name} <{email}>\n\n{message}'

        try:
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
    try:
        projects_ref = db.collection('portfolio_projects')
        docs = projects_ref.stream()
        projects_data = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            
            # Convert image_url to full GCS URL if it's just a filename
            if 'image_url' in data and not data['image_url'].startswith('http'):
                data['image_url'] = get_gcs_url(data['image_url'])
                
            projects_data.append(data)
    except Exception as e:
        flash('Could not load projects at this time.', 'danger')
        logging.error(f"Firestore error: {e}")
        projects_data = []

    return render_template("projects.html", projects=projects_data)

@app.route("/projects/<project_id>")
def project_detail(project_id):
    try:
        project_ref = db.collection('portfolio_projects').document(project_id)
        project = project_ref.get()
        if project.exists:
            project_data = project.to_dict()
            long_md = project_data.get('long_description_md', '')
            # Use 'extra' and 'tables' extensions for GFM-like support
            project_data['long_description_html'] = markdown.markdown(
                long_md,
                extensions=['extra', 'tables', 'fenced_code', 'codehilite', 'sane_lists']
            )

            if 'image_url' in project_data and not project_data['image_url'].startswith('http'):
                project_data['image_url'] = get_gcs_url(project_data['image_url'])
                
        else:
            flash('Project not found.', 'warning')
            return redirect(url_for('projects'))
    except Exception as e:
        flash('Could not load the project at this time.', 'danger')
        logging.error(f"Firestore error: {e}")
        return redirect(url_for('projects'))

    return render_template("project_detail.html", project=project_data)

@app.route("/robots.txt")
def robots():
    return send_from_directory(".", "robots.txt", mimetype="text/plain")

if __name__ == "__main__":
    app.run(...)