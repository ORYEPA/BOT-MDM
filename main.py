# bot.py
import os
import discord
from dotenv import load_dotenv

load_dotenv()                 # Carga variables desde .env
TOKEN = os.getenv("TOKEN")    # Lee TOKEN del .env

if not TOKEN:
    raise RuntimeError("Falta TOKEN en .env")

intents = discord.Intents.default()
intents.message_content = True  # Asegúrate de activarlo en el portal de Discord

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Conectado como {client.user} (ID: {client.user.id})")

@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.content.lower().startswith("!hello"):
        await message.channel.send("Hello!")

client.run(TOKEN)
