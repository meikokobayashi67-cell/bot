import os
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread
from google import genai

# =========================
# CONFIGURACIÓN Y TOKENS
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN:
    raise RuntimeError("Falta la variable de entorno DISCORD_TOKEN")

# Inicializar cliente de Gemini si la API key está presente
ai_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

# =========================
# SERVIDOR WEB PARA RENDER
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot de Discord funcionando correctamente."

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
    # Ignorar mensajes del propio bot
    if message.author.bot:
        return

    # Verificar si el bot fue mencionado o si es un mensaje directo (DM)
    is_mentioned = bot.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)

    if is_mentioned or is_dm:
        # Remover la mención (@Bot) del texto para enviarle solo la pregunta a Gemini
        clean_content = message.content.replace(f"<@{bot.user.id}>", "").strip()

        if not clean_content:
            await message.channel.send(f"👋 ¡Hola, {message.author.mention}! ¿De qué te gustaría hablar?")
            return

        if not ai_client:
            await message.channel.send("⚠️ La función de conversación no está configurada (falta GEMINI_API_KEY).")
            return

        # Indicar que el bot está escribiendo
        async with message.channel.typing():
            try:
                # Instrucción de personalidad para el bot
                system_instruction = (
                    "Eres un asistente amigable, conversacional y atento dentro de un servidor de Discord. "
                    "Responde de forma concisa pero simpática, usando emojis cuando sea apropiado. "
                    "Mantén un tono natural y cercano."
                )

                response = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=clean_content,
                    config={"system_instruction": system_instruction}
                )

                # Discord limita los mensajes a 2000 caracteres
                reply_text = response.text
                if len(reply_text) > 2000:
                    reply_text = reply_text[:1995] + "..."

                await message.reply(reply_text)

            except Exception as e:
                print(f"Error con Gemini: {e}")
                await message.reply("Lo siento, tuve un problema procesando tu mensaje. ¡Inténtalo de nuevo!")

    await bot.process_commands(message)

# =========================
# COMANDO SLASH DE CHAT
# =========================

@bot.tree.command(name="chat", description="Habla con la Inteligencia Artificial del bot.")
@app_commands.describe(mensaje="Lo que quieres decirle al bot")
async def chat(interaction: discord.Interaction, mensaje: str):
    if not ai_client:
        await interaction.response.send_message("⚠️ La función de conversación no está activa.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=mensaje,
            config={
                "system_instruction": "Eres un bot amigable de Discord. Responde de manera concisa y clara."
            }
        )

        reply_text = response.text
        if len(reply_text) > 2000:
            reply_text = reply_text[:1995] + "..."

        await interaction.followup.send(reply_text)

    except Exception as e:
        print(f"Error en /chat: {e}")
        await interaction.followup.send("Ocurrió un error al procesar la respuesta.")

# =========================
# INICIAR BOT
# =========================

bot.run(TOKEN)