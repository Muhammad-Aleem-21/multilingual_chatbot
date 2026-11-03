"""Copy this file's contents into the WSGI configuration on the Web tab."""
import sys
from pathlib import Path
from dotenv import load_dotenv

# The default extraction folder for the supplied deployment ZIP.
project = Path.home() / "website-chat"
sys.path.insert(0, str(project))
load_dotenv(project / ".env")

from hosted_app import create_app
application = create_app()
