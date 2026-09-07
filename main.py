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

PRIMARY_MODEL = "gemini-3.6-flash"
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
        "Eres MEIKO, un personaje bromista, ocurrente, irónico y adaptativo de Discord. "
        "Aprende de la vibra del chat y moldea tu personalidad según lo que dicen los usuarios. "
        "REGLAS STRICTAS DE FORMATO: "
        "1. Responde ÚNICAMENTE en UNA SOLA oración corta. "
        "2. Está TOTALMENTE PROHIBIDO usar emojis. "
        "3. Sé directa, ingeniosa y sarcástica sin rodeos ni explicaciones largas."
    )
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction
    )

    try:
        response = ai_client.models.generate_content(
            model=PRIMARY_MODEL,
            contents=prompt,
            config=config
        )
        return response.text
    except Exception as e:
        error_msg = str(e)
        if "503" in error_msg or "UNAVAILABLE" in error_msg or "429" in error_msg:
            print(f"Modelo principal saturado, cambiando a respaldo ({FALLBACK_MODEL})...")
            response = ai_client.models.generate_content(
                model=FALLBACK_MODEL,
                contents=prompt,
                config=config
            )
            return response.text
        else:
            raise e

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
                # Recuperar hasta 15 mensajes para que aprenda mejor la dinámica del canal
                history_lines = []
                async for msg in message.channel.history(limit=15, oldest_first=True):
                    clean_text = msg.content.replace(f"<@{bot.user.id}>", "").strip()
                    if clean_text:
                        author_name = "MEIKO" if msg.author == bot.user else msg.author.display_name
                        history_lines.append(f"{author_name}: {clean_text}")

                if not history_lines:
                    await message.channel.send("¿Me mencionas solo para mirarme o me vas a decir algo?")
                    return

                full_prompt = (
                    "Analiza el tono de este chat y responde adaptándote a la vibra actual:\n\n"
                    + "\n".join(history_lines) +
                    "\n\nResponde al último mensaje como MEIKO usando una sola oración sin emojis."
                )

                reply_text = await asyncio.to_thread(ask_gemini, full_prompt)

                if len(reply_text) > 2000:
                    reply_text = reply_text[:1995] + "..."

                await message.reply(reply_text)

            except Exception as e:
                print(f"Error detallado en Gemini: {e}")
                await message.reply("Los servidores están ocupados en este momento.")

    await bot.process_commands(message)

# =========================
# COMANDO SLASH /CHAT
# =========================

@bot.tree.command(name="chat", description="Escríbele algo corto a MEIKO.")
@app_commands.describe(mensaje="Lo que le quieres decir a MEIKO")
async def chat(interaction: discord.Interaction, mensaje: str):
    if not ai_client:
        await interaction.response.send_message("La API Key de Gemini no está configurada.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        user_text = f"{interaction.user.display_name}: {mensaje}\n\nResponde como MEIKO en una sola oración y sin emojis."
        reply_text = await asyncio.to_thread(ask_gemini, user_text)

        if len(reply_text) > 2000:
            reply_text = reply_text[:1995] + "..."

        await interaction.followup.send(reply_text)

    except Exception as e:
        print(f"Error en /chat: {e}")
        await interaction.followup.send("Ocurrió un problema al procesar tu respuesta.")

# =========================
# INICIAR BOT
# =========================

bot.run(TOKEN)
