"""Create secret-free ZIP files for browser installation and free hosting."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent
output = root / "dist"
output.mkdir(exist_ok=True)
backend = ["hosted_app.py", "pythonanywhere_wsgi.py", "requirements-hosted.txt",
           "DEPLOY_FREE.md", "chatbot/__init__.py", "chatbot/chatbot.py",
           "chatbot/config.py", "chatbot/language_detect.py", "chatbot/llm.py"]
extension = ["manifest.json", "background.js", "content.js", "options.html", "options.js", "README.md"]
with ZipFile(output / "website-chat-backend.zip", "w", ZIP_DEFLATED) as archive:
    for name in backend:
        archive.write(root / name, name)
with ZipFile(output / "website-chat-extension.zip", "w", ZIP_DEFLATED) as archive:
    for name in extension:
        archive.write(root / "extension" / name, name)
print("Created dist/website-chat-backend.zip and dist/website-chat-extension.zip (no secrets).")
