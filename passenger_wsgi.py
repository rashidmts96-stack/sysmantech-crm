import sys
import os

# Add the application folder to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Import the Flask app and expose it as 'application' (required by Passenger/cPanel)
from app import app as application
