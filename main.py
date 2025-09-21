from datetime import datetime
from flask import Flask, render_template

app = Flask(__name__)

@app.context_processor
def inject_year():
    return {'current_year': datetime.utcnow().year}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/blog")
def blog():
    return render_template("blog.html")

@app.route("/projects")
def projects():
    return render_template("projects.html")

if __name__ == "__main__":
    app.run(debug=True, port=5002)