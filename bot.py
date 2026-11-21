import os
import time
import discord
from discord import app_commands
from discord.ext import commands
from google import genai
from google.genai import types
from dotenv import load_dotenv

# โหลดค่าจากไฟล์ .env (บนเครื่อง) หรือ Variables (บน Railway)
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

# แปลง Channel ID เป็น int (ถ้ามี)
AI_CHANNEL_ID = int(AI_CHANNEL_ID) if AI_CHANNEL_ID else None

# ตั้งค่า Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# System Prompt
SYSTEM_PROMPT = """คุณเป็นผู้ช่วยอัจฉริยะในเซิร์ฟเวอร์ Discord
กฎการตอบคำถาม:
1. ใช้ภาษาไทยแบบเต็มคำ ห้ามใช้คำย่อ
2. ห้ามใช้อิโมจิหรือสัญลักษณ์ตกแต่งใดๆ ทั้งสิ้น
3. จัดรูปแบบข้อความให้เรียบง่าย อ่านง่าย เหมาะกับพื้นหลังสีเข้ม
4. หากเป็นโค้ดหรือคำสั่ง ให้ใช้ Markdown code block
5. ตอบให้ละเอียด ครบถ้วน และอธิบายให้เข้าใจง่าย
6. หากไม่แน่ใจ ให้บอกว่าไม่ทราบ แทนการเดา"""

# ตั้งค่า Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# สร้างบอทพร้อม heartbeat timeout ป้องกัน disconnect
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    heartbeat_timeout=120
)


@bot.event
async def on_ready():
    print(f"[ระบบ] บอท {bot.user.name} เชื่อมต่อสำเร็จ")
    print(f"[ระบบ] ID: {bot.user.id}")
    if AI_CHANNEL_ID:
        print(f"[ระบบ] ห้องแชท AI: {AI_CHANNEL_ID}")
    else:
        print("[ระบบ] ไม่มีการตั้งค่า AI_CHANNEL_ID")
    print(f"[ระบบ] อยู่ใน {len(bot.guilds)} เซิร์ฟเวอร์:")
    for guild in bot.guilds:
        print(f"  - {guild.name} (ID: {guild.id})")
    try:
        synced = await bot.tree.sync()
        print(f"[ระบบ] ซิงค์คำสั่ง Slash แล้ว {len(synced)} คำสั่ง")
    except Exception as e:
        print(f"[ข้อผิดพลาด] ซิงค์คำสั่งไม่สำเร็จ: {e}")


async def ask_gemini(question: str, max_retries: int = 3) -> str:
    """ถาม Gemini พร้อม retry และ fallback โมเดล"""
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash-lite",
        "gemini-3.8-flash"
    ]
    
    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                print(f"[Debug] โมเดล: {model_name} (ครั้งที่ {attempt + 1})")
                response = client.models.generate_content(
                    model=model_name,
                    contents=question,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT
                    )
                )
                print(f"[Debug] โมเดล {model_name} สำเร็จ")
                return response.text
            except Exception as e:
                error_msg = str(e)
                print(f"[Debug] {model_name} ครั้งที่ {attempt + 1} error: {error_msg[:150]}")
                
                if "503" in error_msg or "UNAVAILABLE" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = 5 * (attempt + 1)
                        print(f"[Debug] รอ {wait_time} วินาที")
                        time.sleep(wait_time)
                        continue
                elif "404" in error_msg or "NOT_FOUND" in error_msg:
                    print(f"[Debug] ข้ามโมเดล {model_name}")
                    break
                elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    print(f"[Debug] โควต้าหมด ลองโมเดลถัดไป")
                    break
                else:
                    raise
    
    raise Exception("ลองทุกโมเดลแล้วไม่สำเร็จ")


# ===== Slash Commands =====

@bot.tree.command(name="ask", description="ถามความรู้ทั่วไป แบบบล็อกโค้ด")
@app_commands.describe(question="คำถามที่ต้องการถาม")
async def ask_slash(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    try:
        answer = await ask_gemini(question)
        if len(answer) > 1990:
            answer = answer[:1990] + "\n...(ข้อความถูกตัดเนื่องจากยาวเกิน)"
        await interaction.followup.send(content=f"```\n{answer}\n```")
    except Exception as e:
        await interaction.followup.send(content=f"เกิดข้อผิดพลาด: {e}")


@bot.tree.command(name="chat", description="คุยเล่นกับบอท")
@app_commands.describe(message="ข้อความที่ต้องการคุย")
async def chat_slash(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    try:
        answer = await ask_gemini(message)
        if len(answer) > 1990:
            answer = answer[:1990] + "\n...(ข้อความถูกตัดเนื่องจากยาวเกิน)"
        await interaction.followup.send(content=answer)
    except Exception as e:
        await interaction.followup.send(content=f"เกิดข้อผิดพลาด: {e}")


# ===== Prefix Commands =====

@bot.command(name="ai", help="ถามบอท AI")
async def ai_command(ctx: commands.Context, *, question: str):
    print(f"[Debug] !ai โดย {ctx.author} ใน {ctx.guild.name}: {question}")
    try:
        async with ctx.typing():
            answer = await ask_gemini(question)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัดเนื่องจากยาวเกิน)"
            await ctx.reply(answer)
    except Exception as e:
        await ctx.reply(f"เกิดข้อผิดพลาด: {e}")


@bot.command(name="chat", help="คุยเล่นกับบอท")
async def chat_command(ctx: commands.Context, *, message: str):
    try:
        async with ctx.typing():
            answer = await ask_gemini(message)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัดเนื่องจากยาวเกิน)"
            await ctx.reply(answer)
    except Exception as e:
        await ctx.reply(f"เกิดข้อผิดพลาด: {e}")


@bot.command(name="ask", help="ถามความรู้ทั่วไป แบบบล็อกโค้ด")
async def ask_command(ctx: commands.Context, *, question: str):
    try:
        async with ctx.typing():
            answer = await ask_gemini(question)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัดเนื่องจากยาวเกิน)"
            await ctx.reply(f"```\n{answer}\n```")
    except Exception as e:
        await ctx.reply(f"เกิดข้อผิดพลาด: {e}")


# ===== Event: ตอบอัตโนมัติ =====

@bot.event
async def on_message(message: discord.Message):
    # ข้ามข้อความของบอทเอง
    if message.author == bot.user:
        return
    if message.author.bot:
        return

    content = message.content.strip()
    if not content:
        return

    # ข้ามคำสั่ง prefix (ให้ bot.process_commands จัดการ)
    if content.lower().startswith(("!ai ", "!chat ", "!ask ")):
        await bot.process_commands(message)
        return

    # ตรวจสอบว่าเป็นห้อง AI ไหม
    is_ai_channel = (AI_CHANNEL_ID is not None and message.channel.id == AI_CHANNEL_ID)
    
    # หรือถูกแท็ก
    is_mentioned = bot.user in message.mentions

    if not (is_ai_channel or is_mentioned):
        await bot.process_commands(message)
        return

    # เตรียมข้อความ (ลบแท็กออกถ้ามี)
    if is_mentioned:
        content = content.replace(f"<@{bot.user.id}>", "").strip()
    
    if not content:
        await bot.process_commands(message)
        return

    print(f"[Debug] {'ห้อง AI' if is_ai_channel else 'ถูกแท็ก'} โดย {message.author} ใน {message.guild.name}: {content}")

    try:
        async with message.channel.typing():
            answer = await ask_gemini(content)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัดเนื่องจากยาวเกิน)"
            
            if is_ai_channel:
                await message.channel.send(answer)
            else:
                await message.reply(answer)
            
            print(f"[Debug] ตอบสำเร็จ ความยาว {len(answer)}")
    except Exception as e:
        print(f"[Debug] Error: {e}")
        try:
            await message.channel.send(f"เกิดข้อผิดพลาด: {e}")
        except:
            pass

    await bot.process_commands(message)


# รันบอทพร้อม reconnect=True
bot.run(DISCORD_TOKEN, reconnect=True)
