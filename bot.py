import os
import time
import discord
from discord import app_commands
from discord.ext import commands
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AI_CHANNEL_ID = os.getenv("AI_CHANNEL_ID")

if not DISCORD_TOKEN:
    print("[ข้อผิดพลาด] ไม่พบ DISCORD_TOKEN")
    exit()
if not GEMINI_API_KEY:
    print("[ข้อผิดพลาด] ไม่พบ GEMINI_API_KEY")
    exit()

AI_CHANNEL_ID = int(AI_CHANNEL_ID) if AI_CHANNEL_ID else None

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """คุณคือผู้ช่วย AI อัจฉริยะและเป็นมิตรในเซิร์ฟเวอร์ Discord
- คุณสามารถค้นหาข้อมูลจากอินเทอร์เน็ตได้ เพื่อให้ข้อมูลที่เป็นปัจจุบันและถูกต้อง
- ตอบคำถามให้ตรงประเด็น เป็นธรรมชาติ และอ่านง่าย
- ใช้ภาษาไทยที่สุภาพและเป็นกันเอง
- หากเป็นคำถามทั่วไป ให้ตอบทันทีอย่างมั่นใจ ไม่ต้องปฏิเสธ
- จัดรูปแบบข้อความให้อ่านง่าย"""

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"[ระบบ] บอท {bot.user.name} เชื่อมต่อสำเร็จ")
    print(f"[ระบบ] ID: {bot.user.id}")
    try:
        synced = await bot.tree.sync()
        print(f"[ระบบ] ซิงค์คำสั่ง Slash แล้ว {len(synced)} คำสั่ง")
    except Exception as e:
        print(f"[ข้อผิดพลาด] ซิงค์คำสั่งไม่สำเร็จ: {e}")


async def ask_gemini(question: str, max_retries: int = 2) -> str:
    models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash"]

    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                print(f"[Debug] กำลังประมวลผลด้วย {model_name}...")
                config = types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
                # ใช้ client.aio = async ไม่บล็อก event loop
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=question,
                    config=config
                )
                print(f"[Debug] ตอบสำเร็จ")
                return response.text

            except Exception as e:
                error_msg = str(e)
                print(f"[Debug] {model_name} error: {error_msg[:150]}")
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    break
                elif "404" in error_msg or "NOT_FOUND" in error_msg:
                    break
                elif "503" in error_msg or "UNAVAILABLE" in error_msg:
                    if attempt < max_retries - 1:
                        await asyncio_sleep(5 * (attempt + 1))
                        continue
                else:
                    raise

    raise Exception("ไม่สามารถประมวลผลได้ในขณะนี้")


async def asyncio_sleep(seconds):
    import asyncio
    await asyncio.sleep(seconds)


@bot.tree.command(name="ask", description="ถามความรู้ทั่วไป")
@app_commands.describe(question="คำถามที่ต้องการถาม")
async def ask_slash(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    try:
        answer = await ask_gemini(question)
        if len(answer) > 1990:
            answer = answer[:1990] + "\n...(ข้อความถูกตัด)"
        await interaction.followup.send(content=answer)
    except Exception as e:
        await interaction.followup.send(content=f"เกิดข้อผิดพลาด: {e}")


@bot.tree.command(name="chat", description="คุยเล่นกับบอท")
@app_commands.describe(message="ข้อความที่ต้องการคุย")
async def chat_slash(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    try:
        answer = await ask_gemini(message)
        if len(answer) > 1990:
            answer = answer[:1990] + "\n...(ข้อความถูกตัด)"
        await interaction.followup.send(content=answer)
    except Exception as e:
        await interaction.followup.send(content=f"เกิดข้อผิดพลาด: {e}")


@bot.command(name="ai", help="ถามบอท AI")
async def ai_command(ctx: commands.Context, *, question: str):
    try:
        async with ctx.typing():
            answer = await ask_gemini(question)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัด)"
            await ctx.reply(answer)
    except Exception as e:
        await ctx.reply(f"เกิดข้อผิดพลาด: {e}")


@bot.command(name="chat", help="คุยเล่นกับบอท")
async def chat_command(ctx: commands.Context, *, message: str):
    try:
        async with ctx.typing():
            answer = await ask_gemini(message)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัด)"
            await ctx.reply(answer)
    except Exception as e:
        await ctx.reply(f"เกิดข้อผิดพลาด: {e}")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or message.author.bot:
        return

    content = message.content.strip()
    if not content:
        return

    if content.lower().startswith(("!ai ", "!chat ", "!ask ")):
        await bot.process_commands(message)
        return

    is_ai_channel = (AI_CHANNEL_ID is not None and message.channel.id == AI_CHANNEL_ID)
    is_mentioned = bot.user in message.mentions

    if not (is_ai_channel or is_mentioned):
        await bot.process_commands(message)
        return

    if is_mentioned:
        content = content.replace(f"<@{bot.user.id}>", "").strip()

    if not content:
        await bot.process_commands(message)
        return

    print(f"[Debug] {'ห้อง AI' if is_ai_channel else 'ถูกแท็ก'} โดย {message.author}: {content}")

    try:
        async with message.channel.typing():
            answer = await ask_gemini(content)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัด)"

            if is_ai_channel:
                await message.channel.send(answer)
            else:
                await message.reply(answer)
    except Exception as e:
        print(f"[Debug] Error: {e}")
        try:
            await message.channel.send(f"เกิดข้อผิดพลาด: {e}")
        except:
            pass

    await bot.process_commands(message)


bot.run(DISCORD_TOKEN, reconnect=True)
