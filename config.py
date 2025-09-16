
import os
import json

#------load token from .env file----------------------------------------------------------------------------------------------------------------------------------------




with open("config.json", "r") as f: 
    settings = json.load(f)

def load_config():
    if not os.path.exists("config.json"):
        with open("config.json", "w") as f:
            json.dump({}, f, indent=4)
    with open("config.json", "r") as f:
        return json.load(f)

def save_config(data, filename="config.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

async def sendlog(channel, message: str):
    print(message)
    await channel.send(f"➡️{message}")
