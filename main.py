from datetime import datetime
from flask import Flask, render_template, flash, redirect, url_for
from forms import ContactForm
from flask_mail import Mail, Message
from dotenv import load_dotenv
import os
import logging

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


mail = Mail(app)

# Configure logging (at the top of your file, after imports)
logging.basicConfig(level=logging.INFO)

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

@app.route("/blog")
def blog():
    return render_template("blog.html")

@app.route("/projects")
def projects():
    return render_template("projects.html")

if __name__ == "__main__":
    app.run(debug=True, port=5002)