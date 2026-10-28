"""
list_models.py  -  prints the model names your Groq key can use RIGHT NOW.

Groq adds and removes models over time. If a model name in chatbot/config.py gives
a "model not found" error, run this, pick a name from the list and paste it into
config.py.

Run it:   python list_models.py
"""

from groq import Groq

from chatbot.config import GROQ_API_KEY

if not GROQ_API_KEY or GROQ_API_KEY == "paste_your_key_here":
    raise SystemExit("No key found. Copy .env.example to .env and add your GROQ_API_KEY.")

client = Groq(api_key=GROQ_API_KEY)
for model in sorted(client.models.list().data, key=lambda m: m.id):
    print(model.id)
