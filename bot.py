import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
from discord.ext import commands
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
AI_CHANNEL_ID = os.getenv("AI_CHANNEL_ID")

if not DISCORD_TOKEN:
    print("[ข้อผิดพลาด] ไม่พบ DISCORD_TOKEN")
    exit()
if not GROQ_API_KEY:
    print("[ข้อผิดพลาด] ไม่พบ GROQ_API_KEY")
    exit()

AI_CHANNEL_ID = int(AI_CHANNEL_ID) if AI_CHANNEL_ID else None

client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

DAY_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
MONTH_TH = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]

def get_current_time_th():
    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    return f"วันนี้คือวัน{DAY_TH[now.weekday()]}ที่ {now.day} {MONTH_TH[now.month - 1]} พ.ศ. {now.year + 543} เวลา {now.strftime('%H:%M')} น."

def build_system_prompt():
    return f"""คุณคือผู้ช่วย AI ในเซิร์ฟเวอร์ Discord
ข้อมูลปัจจุบัน: {get_current_time_th()}
กฎ: ใช้ภาษาไทยสุภาพ เป็นธรรมชาติ ห้ามใช้อิโมจิ ตอบตรงประเด็น"""

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[ระบบ] บอท {bot.user.name} เชื่อมต่อสำเร็จ")
    print(f"[ระบบ] {get_current_time_th()}")
    try:
        synced = await bot.tree.sync()
        print(f"[ระบบ] ซิงค์ {len(synced)} คำสั่ง")
    except Exception as e:
        print(f"[ข้อผิดพลาด] {e}")

async def ask_ai(question: str) -> str:
    models_to_try = [
        "llama-3.3-70b-specdec",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768"
    ]
    
    for model in models_to_try:
        try:
            print(f"[Debug] ลอง: {model}")
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": question}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            print(f"[Debug] {model} สำเร็จ")
            return response.choices[0].message.content
        except Exception as e:
            msg = str(e)
            print(f"[Debug] {model} error: {msg[:150]}")
            if "404" in msg or "does not exist" in msg:
                continue
            raise
    
    raise Exception("ไม่มีโมเดลที่ใช้งานได้")

async def send_answer(channel, question):
    print(f"[Debug] กำลังถาม AI: {question}")
    try:
        answer = await ask_ai(question)
        print(f"[Debug] ได้คำตอบ ความยาว {len(answer)}")
        if len(answer) > 1990:
            answer = answer[:1990] + "\n...(ข้อความถูกตัด)"
        await channel.send(answer)
        print(f"[Debug] ส่งข้อความสำเร็จ")
    except Exception as e:
        print(f"[Debug] Error: {e}")
        try:
            await channel.send(f"เกิดข้อผิดพลาด: {e}")
            print(f"[Debug] ส่ง error message สำเร็จ")
        except Exception as e2:
            print(f"[Debug] ส่ง error message ไม่สำเร็จ: {e2}")

@bot.tree.command(name="ask", description="ถามความรู้ทั่วไป")
@app_commands.describe(question="คำถาม")
async def ask_slash(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    try:
        answer = await ask_ai(question)
        await interaction.followup.send(answer)
    except Exception as e:
        await interaction.followup.send(f"เกิดข้อผิดพลาด: {e}")

@bot.tree.command(name="chat", description="คุยเล่นกับบอท")
@app_commands.describe(message="ข้อความ")
async def chat_slash(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    try:
        answer = await ask_ai(message)
        await interaction.followup.send(answer)
    except Exception as e:
        await interaction.followup.send(f"เกิดข้อผิดพลาด: {e}")

@bot.command(name="ai")
async def ai_command(ctx, *, question: str):
    print(f"[Debug] !ai โดย {ctx.author}: {question}")
    await send_answer(ctx.channel, question)

@bot.command(name="chat")
async def chat_command(ctx, *, message: str):
    print(f"[Debug] !chat โดย {ctx.author}: {message}")
    await send_answer(ctx.channel, message)

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
    
    is_ai_channel = AI_CHANNEL_ID and message.channel.id == AI_CHANNEL_ID
    is_mentioned = bot.user in message.mentions
    
    if not (is_ai_channel or is_mentioned):
        await bot.process_commands(message)
        return
    
    if is_mentioned:
        content = content.replace(f"<@{bot.user.id}>", "").strip()
    
    if not content:
        await bot.process_commands(message)
        return
    
    print(f"[Debug] on_message: {content}")
    await send_answer(message.channel, content)
    await bot.process_commands(message)

bot.run(DISCORD_TOKEN, reconnect=True)
