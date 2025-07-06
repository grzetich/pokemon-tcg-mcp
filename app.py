from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    """
    A simple home route to confirm the Flask app is running.
    """
    print("INFO: Minimal Flask App Home route accessed.")
    return "Minimal Flask App is running successfully on Heroku!"

# This block is for local development only and is NOT executed by Gunicorn on Heroku.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)