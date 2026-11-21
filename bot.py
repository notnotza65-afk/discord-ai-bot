import os
from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
AI_CHANNEL_ID = os.getenv("AI_CHANNEL_ID")

if not DISCORD_TOKEN or not OPENROUTER_API_KEY:
    print("[ข้อผิดพลาด] ไม่พบ Token หรือ API Key")
    exit()

AI_CHANNEL_ID = int(AI_CHANNEL_ID) if AI_CHANNEL_ID else None

client = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

DAY_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
MONTH_TH = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]

def get_time_th():
    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    return f"วัน{DAY_TH[now.weekday()]}ที่ {now.day} {MONTH_TH[now.month-1]} พ.ศ. {now.year+543} เวลา {now.strftime('%H:%M')} น."

SYSTEM_PROMPT = f"""คุณคือผู้ช่วย AI ใน Discord
ข้อมูลปัจจุบัน: {get_time_th()}
กฎ: ใช้ภาษาไทยสุภาพ เป็นธรรมชาติ ห้ามใช้อิโมจิ ตอบตรงประเด็น"""

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[ระบบ] บอท {bot.user.name} ออนไลน์")
    print(f"[ระบบ] เวลา: {get_time_th()}")
    await bot.tree.sync()

async def ask_ai(q: str) -> str:
    r = await client.chat.completions.create(
        model="meta-llama/llama-3.1-8b-instruct:free",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": q}
        ],
        max_tokens=1000
    )
    return r.choices[0].message.content

async def send_answer(channel, q):
    print(f"[Debug] ถาม: {q}")
    try:
        a = await ask_ai(q)
        print(f"[Debug] ได้คำตอบ {len(a)} ตัว")
        if len(a) > 1990:
            a = a[:1990] + "\n...(ตัด)"
        await channel.send(a)
        print("[Debug] ส่งสำเร็จ")
    except Exception as e:
        print(f"[Debug] Error: {e}")
        await channel.send(f"Error: {e}")

@bot.command(name="ai")
async def ai_cmd(ctx, *, q: str):
    await send_answer(ctx.channel, q)

@bot.event
async def on_message(m):
    if m.author == bot.user or m.author.bot:
        return
    c = m.content.strip()
    if not c:
        return
    if c.lower().startswith("!ai "):
        await bot.process_commands(m)
        return
    is_ai = AI_CHANNEL_ID and m.channel.id == AI_CHANNEL_ID
    is_tag = bot.user in m.mentions
    if not (is_ai or is_tag):
        await bot.process_commands(m)
        return
    if is_tag:
        c = c.replace(f"<@{bot.user.id}>", "").strip()
    if not c:
        return
    print(f"[Debug] on_message: {c}")
    await send_answer(m.channel, c)
    await bot.process_commands(m)

bot.run(DISCORD_TOKEN, reconnect=True)
