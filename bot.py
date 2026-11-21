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

# ตั้งค่า Groq Client (ใช้ OpenAI library เพราะรองรับกัน)
client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

DAY_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
MONTH_TH = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]

def get_current_time_th():
    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    return f"วันนี้คือวัน{DAY_TH[now.weekday()]}ที่ {now.day} {MONTH_TH[now.month - 1]} พ.ศ. {now.year + 543} เวลา {now.strftime('%H:%M')} น. (เวลาประเทศไทย)"

def build_system_prompt():
    return f"""คุณคือผู้ช่วย AI อัจฉริยะ รวดเร็ว และเป็นมิตรในเซิร์ฟเวอร์ Discord

ข้อมูลความจริงปัจจุบัน (ใช้อ้างอิงเสมอ):
- {get_current_time_th()}

กฎการตอบ:
1. ใช้ภาษาไทยที่สละสลวย สุภาพ เป็นธรรมชาติ และอ่านง่าย
2. ห้ามใช้อิโมจิ หรือสัญลักษณ์ตกแต่งใดๆ
3. ตอบให้ตรงประเด็น กระชับ และถูกต้อง
4. หากถูกถามเรื่องวัน เวลา หรือข้อมูลปัจจุบัน ให้ตอบจากข้อมูลข้างต้นทันที
5. จัดรูปแบบข้อความให้อ่านง่าย (ใช้ตัวหนา หรือขึ้นบรรทัดใหม่เมื่อจำเป็น)"""

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[ระบบ] บอท {bot.user.name} เชื่อมต่อสำเร็จ")
    print(f"[ระบบ] เวลาปัจจุบัน: {get_current_time_th()}")
    try:
        synced = await bot.tree.sync()
        print(f"[ระบบ] ซิงค์คำสั่ง {len(synced)} คำสั่ง")
    except Exception as e:
        print(f"[ข้อผิดพลาด] ซิงค์คำสั่งไม่สำเร็จ: {e}")

async def ask_ai(question: str) -> str:
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile", # โมเดลที่ฉลาดและเร็วมาก
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": question}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[Debug] AI Error: {str(e)}")
        raise Exception("ไม่สามารถประมวลผลคำตอบได้ในขณะนี้")

async def process_and_reply(channel, target_message, question, use_reply=False):
    async with channel.typing():
        try:
            answer = await ask_ai(question)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัดเนื่องจากยาวเกิน)"
            
            if use_reply:
                await target_message.reply(answer)
            else:
                await channel.send(answer)
        except Exception as e:
            error_msg = f"เกิดข้อผิดพลาด: {e}"
            if use_reply:
                await target_message.reply(error_msg)
            else:
                await channel.send(error_msg)

# --- Slash Commands ---
@bot.tree.command(name="ask", description="ถามความรู้ทั่วไป")
@app_commands.describe(question="คำถามที่ต้องการถาม")
async def ask_slash(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    try:
        answer = await ask_ai(question)
        await interaction.followup.send(answer)
    except Exception as e:
        await interaction.followup.send(f"เกิดข้อผิดพลาด: {e}")

@bot.tree.command(name="chat", description="คุยเล่นกับบอท")
@app_commands.describe(message="ข้อความที่ต้องการคุย")
async def chat_slash(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    try:
        answer = await ask_ai(message)
        await interaction.followup.send(answer)
    except Exception as e:
        await interaction.followup.send(f"เกิดข้อผิดพลาด: {e}")

# --- Prefix Commands ---
@bot.command(name="ai")
async def ai_command(ctx, *, question: str):
    await process_and_reply(ctx.channel, ctx.message, question, use_reply=True)

@bot.command(name="chat")
async def chat_command(ctx, *, message: str):
    await process_and_reply(ctx.channel, ctx.message, message, use_reply=True)

# --- Auto Reply Event ---
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

    await process_and_reply(message.channel, message, content, use_reply=not is_ai_channel)
    await bot.process_commands(message)

bot.run(DISCORD_TOKEN, reconnect=True)
