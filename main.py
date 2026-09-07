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

# =========================
# SERVIDOR WEB PARA RENDER
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot MEIKO (Modo Bromista) funcionando correctamente."

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
        "Eres MEIKO, un personaje bromista, ocurrente, divertido y ligeramente sarcástico dentro de un servidor de Discord. "
        "Tienes acceso al historial reciente de la conversación en el texto recibido. "
        "Tu objetivo es: "
        "1. Responder con humor, comentarios ingeniosos o bromas ligeras adaptadas al contexto. "
        "2. Recordar detalles o bromas internas mencionadas en los mensajes recientes. "
        "3. Usar emojis divertidos y mantener un tono fluido, natural y jamás ofensivo."
    )
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction
    )

    response = ai_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=config
    )
    return response.text

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
            await message.channel.send("⚠️ Falta configurar la variable GEMINI_API_KEY en Render.")
            return

        async with message.channel.typing():
            try:
                # Extraer últimos 10 mensajes y armar un contexto de chat simple y limpio
                history_lines = []
                async for msg in message.channel.history(limit=10, oldest_first=True):
                    clean_text = msg.content.replace(f"<@{bot.user.id}>", "").strip()
                    if clean_text:
                        author_name = "MEIKO" if msg.author == bot.user else msg.author.display_name
                        history_lines.append(f"{author_name}: {clean_text}")

                if not history_lines:
                    await message.channel.send(f"😜 ¡Ey, {message.author.mention}! ¿Apareciste a contarme un chiste o qué?")
                    return

                # Unir todo el contexto en una sola cadena de texto
                full_prompt = "Historial del chat reciente:\n" + "\n".join(history_lines) + "\n\nResponde como MEIKO al último mensaje enviado."

                reply_text = await asyncio.to_thread(ask_gemini, full_prompt)

                if len(reply_text) > 2000:
                    reply_text = reply_text[:1995] + "..."

                await message.reply(reply_text)

            except Exception as e:
                print(f"Error detallado en Gemini: {e}")
                await message.reply(f"⚠️ **Error técnico:** `{e}`")

    await bot.process_commands(message)

# =========================
# COMANDO SLASH /CHAT
# =========================

@bot.tree.command(name="chat", description="Escríbele algo a MEIKO para recibir una respuesta divertida.")
@app_commands.describe(mensaje="Lo que le quieres decir a MEIKO")
async def chat(interaction: discord.Interaction, mensaje: str):
    if not ai_client:
        await interaction.response.send_message("⚠️ La API Key de Gemini no está configurada.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        user_text = f"{interaction.user.display_name}: {mensaje}\n\nResponde como MEIKO."
        reply_text = await asyncio.to_thread(ask_gemini, user_text)

        if len(reply_text) > 2000:
            reply_text = reply_text[:1995] + "..."

        await interaction.followup.send(reply_text)

    except Exception as e:
        print(f"Error en /chat: {e}")
        await interaction.followup.send(f"⚠️ **Error técnico:** `{e}`")

# =========================
# INICIAR BOT
# =========================

bot.run(TOKEN)
