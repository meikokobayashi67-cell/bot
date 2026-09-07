import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread
from google import genai
from google.genai import types

# =========================
# CONFIGURACIÓN Y TOKENS
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN:
    raise RuntimeError("Falta la variable de entorno DISCORD_TOKEN")

ai_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-1.5-flash"

# =========================
# SERVIDOR WEB PARA RENDER
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot MEIKO funcionando correctamente."

@app.route("/health")
def health():
    return "OK"

@app.route("/tos")
def tos():
    return "<h1>Condiciones del Servicio</h1><p>Bot de uso personal en Discord.</p>"

@app.route("/privacy")
def privacy():
    return "<h1>Política de Privacidad</h1><p>No se almacenan datos personales fuera de la sesión.</p>"

def run_web():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web, daemon=True).start()

# =========================
# CONFIGURACIÓN DE DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

def ask_gemini(prompt: str) -> str:
    system_instruction = (
        "Eres MEIKO, un personaje sarcástico, directo e ingenioso en Discord. "
        "Adáptate al tono de los usuarios según el historial. "
        "REGLAS OBLIGATORIAS: "
        "1. Escribe SOLO UNA oración muy corta (máximo 15 palabras). "
        "2. NUNCA uses emojis ni emoticonos. "
        "3. Sé concisa y ácida."
    )
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        max_output_tokens=80,  # Limita físicamente la longitud del mensaje
        temperature=0.8
    )

    try:
        response = ai_client.models.generate_content(
            model=PRIMARY_MODEL,
            contents=prompt,
            config=config
        )
        return response.text.strip()
    except Exception as e:
        print(f"[Error con {PRIMARY_MODEL}]: {e}")
        try:
            response = ai_client.models.generate_content(
                model=FALLBACK_MODEL,
                contents=prompt,
                config=config
            )
            return response.text.strip()
        except Exception as err2:
            print(f"[Error con {FALLBACK_MODEL}]: {err2}")
            raise err2

# =========================
# EVENTOS DE DISCORD
# =========================

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Error sincronizando comandos: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    is_mentioned = bot.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)

    if is_mentioned or is_dm:
        if not ai_client:
            await message.channel.send("Falta configurar la variable GEMINI_API_KEY en Render.")
            return

        async with message.channel.typing():
            try:
                history_lines = []
                async for msg in message.channel.history(limit=10, oldest_first=True):
                    clean_text = msg.content.replace(f"<@{bot.user.id}>", "").strip()
                    if clean_text:
                        author_name = "MEIKO" if msg.author == bot.user else msg.author.display_name
                        history_lines.append(f"{author_name}: {clean_text}")

                if not history_lines:
                    await message.channel.send("Di algo coherente si quieres que responda.")
                    return

                full_prompt = (
                    "Historial del chat para aprender el contexto:\n"
                    + "\n".join(history_lines) +
                    "\n\nResponde únicamente al último mensaje siguiendo las reglas."
                )

                reply_text = await asyncio.to_thread(ask_gemini, full_prompt)
                await message.reply(reply_text)

            except Exception as e:
                print(f"Error procesando mensaje: {e}")
                await message.reply(f"Error en el sistema: {e}")

    await bot.process_commands(message)

# =========================
# COMANDO SLASH /CHAT
# =========================

@bot.tree.command(name="chat", description="Escríbele algo a MEIKO.")
@app_commands.describe(mensaje="Lo que le quieres decir a MEIKO")
async def chat(interaction: discord.Interaction, mensaje: str):
    if not ai_client:
        await interaction.response.send_message("La API Key de Gemini no está configurada.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        user_text = f"{interaction.user.display_name}: {mensaje}"
        reply_text = await asyncio.to_thread(ask_gemini, user_text)
        await interaction.followup.send(reply_text)

    except Exception as e:
        print(f"Error en /chat: {e}")
        await interaction.followup.send(f"Error: {e}")

# =========================
# INICIAR BOT
# =========================

bot.run(TOKEN)
