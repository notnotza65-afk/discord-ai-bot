import os
import sys
import traceback
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

if not DISCORD_TOKEN:
    print("[FATAL] ไม่พบ DISCORD_TOKEN")
    sys.exit(1)
if not OPENROUTER_API_KEY:
    print("[FATAL] ไม่พบ OPENROUTER_API_KEY")
    sys.exit(1)

AI_CHANNEL_ID = int(AI_CHANNEL_ID) if AI_CHANNEL_ID else None

client = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

DAY_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
MONTH_TH = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]

def get_time_th():
    try:
        now = datetime.now(ZoneInfo("Asia/Bangkok"))
        return f"วัน{DAY_TH[now.weekday()]}ที่ {now.day} {MONTH_TH[now.month-1]} พ.ศ. {now.year+543} เวลา {now.strftime('%H:%M')} น."
    except Exception as e:
        return f"ไม่สามารถดึงเวลาได้: {e}"

SYSTEM_PROMPT = """คุณคือผู้ช่วย AI ใน Discord
กฎ: ใช้ภาษาไทยสุภาพ เป็นธรรมชาติ ห้ามใช้อิโมจิ ตอบตรงประเด็น"""

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    try:
        print(f"[ระบบ] บอท {bot.user.name} ออนไลน์")
        print(f"[ระบบ] เวลา: {get_time_th()}")
        print(f"[ระบบ] AI Channel ID: {AI_CHANNEL_ID}")
        print(f"[ระบบ] OpenRouter Key: {OPENROUTER_API_KEY[:10]}...")
        synced = await bot.tree.sync()
        print(f"[ระบบ] ซิงค์ {len(synced)} คำสั่ง")
        print("[ระบบ] พร้อมใช้งาน!")
    except Exception as e:
        print(f"[ERROR on_ready] {e}")
        traceback.print_exc()

async def ask_ai(q: str) -> str:
    try:
        time_info = get_time_th()
        full_prompt = f"{SYSTEM_PROMPT}\nข้อมูลปัจจุบัน: {time_info}"
        
        print(f"[AI] กำลังถาม OpenRouter...")
        r = await client.chat.completions.create(
            model="meta-llama/llama-3.1-8b-instruct:free",
            messages=[
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": q}
            ],
            max_tokens=1000
        )
        answer = r.choices[0].message.content
        print(f"[AI] ได้คำตอบ {len(answer)} ตัวอักษร")
        return answer
    except Exception as e:
        print(f"[AI ERROR] {e}")
        traceback.print_exc()
        raise

async def send_answer(channel, q):
    try:
        print(f"[Send] กำลังประมวลผล: {q[:50]}...")
        a = await ask_ai(q)
        if len(a) > 1990:
            a = a[:1990] + "\n...(ตัด)"
        await channel.send(a)
        print(f"[Send] ส่งสำเร็จ")
    except Exception as e:
        print(f"[Send ERROR] {e}")
        traceback.print_exc()
        try:
            await channel.send(f"เกิดข้อผิดพลาด: {e}")
        except Exception as e2:
            print(f"[Send ERROR 2] {e2}")

@bot.event
async def on_command_error(ctx, error):
    try:
        print(f"[Command Error] {error}")
        await ctx.send(f"Error: {error}")
    except:
        pass

@bot.command(name="ai")
async def ai_cmd(ctx, *, q: str):
    try:
        print(f"[Command] !ai โดย {ctx.author}: {q}")
        await send_answer(ctx.channel, q)
    except Exception as e:
        print(f"[Command ERROR] {e}")
        try:
            await ctx.send(f"Error: {e}")
        except:
            pass

@bot.command(name="test")
async def test_cmd(ctx):
    try:
        await ctx.send("บอททำงานปกติ!")
    except Exception as e:
        print(f"[Test ERROR] {e}")

@bot.event
async def on_message(m):
    try:
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
        
        print(f"[Message] โดย {m.author}: {c[:50]}...")
        await send_answer(m.channel, c)
        await bot.process_commands(m)
    except Exception as e:
        print(f"[on_message ERROR] {e}")
        traceback.print_exc()

bot.run(DISCORD_TOKEN, reconnect=True)
