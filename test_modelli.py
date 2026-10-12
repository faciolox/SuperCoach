import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("Modelli Flash disponibili:")
for model in client.models.list():
    if "flash" in model.name.lower():
        print(f"- {model.name}")