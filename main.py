import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# OpenAI SDK (v1)
from openai import AsyncOpenAI

load_dotenv()
DISCORD_TOKEN = os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not DISCORD_TOKEN:
    raise RuntimeError("Falta TOKEN en .env")
if not OPENAI_API_KEY:
    raise RuntimeError("Falta OPENAI_API_KEY en .env")

# Intents
intents = discord.Intents.default()
intents.message_content = True  # Necesario solo si usarás comandos de texto (!ia)

# Bot con comandos híbridos (slash + texto)
bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    intents=intents,
    help_command=None,
)

# OpenAI cliente async
oai = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Sincronizar slash commands al arrancar
async def _setup_hook():
    try:
        await bot.tree.sync()
    except Exception as e:
        print(f"⚠️ No pude sincronizar slash commands: {e}")

bot.setup_hook = _setup_hook

@bot.event
async def on_ready():
    print(f"✅ Conectado como {bot.user} (ID: {bot.user.id})")

# Comando híbrido: funciona como /ia y también !ia <pregunta>
@bot.hybrid_command(name="ia", description="Pregunta a la IA y recibe una respuesta.")
async def ia(ctx: commands.Context, *, prompt: str):
    """Ejemplo: /ia ¿Cómo optimizo una consulta SQL?
       o        !ia ¿Cómo optimizo una consulta SQL?
    """
    # Para slash commands: muestra "pensando..."
    try:
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.defer()
    except Exception:
        pass

    # Llama a OpenAI (modelo económico y bueno para chat largo)
    try:
        completion = await oai.chat.completions.create(
            model="gpt-4o-mini",  # rápido y barato para respuestas complejas
            temperature=0.7,
            messages=[
                {"role": "system", "content": "Eres un asistente experto. Responde en español con claridad y precisión."},
                {"role": "user", "content": prompt},
            ],
        )
        answer = completion.choices[0].message.content.strip()
    except Exception as e:
        answer = f"Lo siento, hubo un error consultando la IA: `{e}`"

    # Responder
    try:
        if hasattr(ctx, "reply"):
            await ctx.reply(answer)
        else:
            await ctx.send(answer)
    except discord.HTTPException:
        # Mensajes largos: envía como archivo si excede límites
        from io import BytesIO
        bio = BytesIO(answer.encode("utf-8"))
        await ctx.send(file=discord.File(bio, filename="respuesta.txt"))

# (Opcional) Comando ping de prueba
@bot.hybrid_command(name="ping", description="Latencia del bot.")
async def ping(ctx: commands.Context):
    await ctx.reply(f"Pong! {round(bot.latency * 1000)}ms")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
