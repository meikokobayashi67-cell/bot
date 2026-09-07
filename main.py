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

# Inicializar cliente de Gemini
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

# Función para consultar a Gemini con la personalidad bromista e historial
def ask_gemini_with_history(contents_list) -> str:
    system_instruction = (
        "Eres MEIKO, un personaje bromista, ocurrente, divertido y ligeramente sarcástico dentro de un servidor de Discord. "
        "Tienes acceso al historial reciente de la conversación. "
        "Tu objetivo es: "
        "1. Responder con humor, comentarios ingeniosos o bromas ligeras adaptadas al contexto actual. "
        "2. Recordar detalles, nombres o bromas internas que hayan ocurrido en los mensajes recientes. "
        "3. Usar emojis divertidos, exagerar un poco las situaciones para hacer reír y mantener un tono muy fluido y natural. "
        "4. Ser amistosa y juguetona, jamás ofensiva o hiriente."
    )
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction
    )

    response = ai_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=contents_list,
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
                # Recuperar los últimos 12 mensajes para que tenga más contexto para sus bromas
                history_messages = []
                async for msg in message.channel.history(limit=12, oldest_first=True):
                    if not msg.content:
                        continue
                    
                    role = "model" if msg.author == bot.user else "user"
                    clean_msg = msg.content.replace(f"<@{bot.user.id}>", "").strip()
                    
                    if clean_msg:
                        # Formateamos indicando quién dijo qué para que sepa a quién hacerle la broma
                        user_name = msg.author.display_name if role == "user" else "MEIKO"
                        content_text = f"{user_name}: {clean_msg}" if role == "user" else clean_msg
                        
                        history_messages.append(
                            types.Content(
                                role=role,
                                parts=[types.Part.from_text(text=content_text)]
                            )
                        )

                if not history_messages:
                    await message.channel.send(f"😜 ¡Ey, {message.author.mention}! ¿Apareciste a contarme un chiste o qué?")
                    return

                reply_text = await asyncio.to_thread(ask_gemini_with_history, history_messages)

                if len(reply_text) > 2000:
                    reply_text = reply_text[:1995] + "..."

                await message.reply(reply_text)

            except Exception as e:
                print(f"Error detallado en Gemini: {e}")
                await message.reply("Se me trabó un circuito intentando pensar en un chiste. ¡Inténtalo de nuevo! 🤖💥")

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
        user_text = f"{interaction.user.display_name}: {mensaje}"
        prompt_content = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_text)]
            )
        ]
        
        reply_text = await asyncio.to_thread(ask_gemini_with_history, prompt_content)

        if len(reply_text) > 2000:
            reply_text = reply_text[:1995] + "..."

        await interaction.followup.send(reply_text)

    except Exception as e:
        print(f"Error en /chat: {e}")
        await interaction.followup.send("Se cayó el chiste... ocurrió un error procesando tu mensaje. 🙈")

# =========================
# INICIAR BOT
# =========================

bot.run(TOKEN)
