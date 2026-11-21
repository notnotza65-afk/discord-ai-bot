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
    print("[ข้อผิดพลาด] ไม่พบ DISCORD_TOKEN ในไฟล์ .env")
    exit()
if not GEMINI_API_KEY:
    print("[ข้อผิดพลาด] ไม่พบ GEMINI_API_KEY ในไฟล์ .env")
    exit()

# แปลง Channel ID เป็น int (ถ้าไม่ใส่จะเป็น None)
AI_CHANNEL_ID = int(AI_CHANNEL_ID) if AI_CHANNEL_ID else None

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """คุณเป็นผู้ช่วยอัจฉริยะในเซิร์ฟเวอร์ Discord
กฎการตอบคำถาม:
1. ใช้ภาษาไทยแบบเต็มคำ ห้ามใช้คำย่อ
2. ห้ามใช้อิโมจิหรือสัญลักษณ์ตกแต่งใดๆ ทั้งสิ้น
3. จัดรูปแบบข้อความให้เรียบง่าย อ่านง่าย เหมาะกับพื้นหลังสีเข้ม
4. หากเป็นโค้ดหรือคำสั่ง ให้ใช้ Markdown code block
5. ตอบให้ละเอียด ครบถ้วน และอธิบายให้เข้าใจง่าย
6. หากไม่แน่ใจ ให้บอกว่าไม่ทราบ แทนการเดา"""

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"[ระบบ] บอท {bot.user.name} เชื่อมต่อสำเร็จ")
    print(f"[ระบบ] ID: {bot.user.id}")
    if AI_CHANNEL_ID:
        print(f"[ระบบ] ห้องแชท AI: {AI_CHANNEL_ID}")
    else:
        print("[ระบบ] ยังไม่ได้ตั้งค่า AI_CHANNEL_ID (บอทจะตอบเฉพาะเมื่อถูกแท็ก)")
    try:
        synced = await bot.tree.sync()
        print(f"[ระบบ] ซิงค์คำสั่ง Slash แล้ว {len(synced)} คำสั่ง")
    except Exception as e:
        print(f"[ข้อผิดพลาด] ซิงค์คำสั่งไม่สำเร็จ: {e}")


async def ask_gemini(question: str, max_retries: int = 3) -> str:
    models_to_try = [
    "gemini-3.8-flash",
    "gemini-2.5-pro",
    "gemini-1.5-pro",
    "gemini-pro"
]
    
    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                print(f"[Debug] กำลังใช้โมเดล: {model_name} (ลองครั้งที่ {attempt + 1})")
                response = client.models.generate_content(
                    model=model_name,
                    contents=question,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT
                    )
                )
                print(f"[Debug] โมเดล {model_name} ทำงานสำเร็จ")
                return response.text
            except Exception as e:
                error_msg = str(e)
                print(f"[Debug] โมเดล {model_name} ลองครั้งที่ {attempt + 1} เกิดข้อผิดพลาด: {error_msg[:100]}")
                
                if "503" in error_msg or "UNAVAILABLE" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = 5 * (attempt + 1)
                        print(f"[Debug] โมเดลไม่ว่าง รอ {wait_time} วินาทีแล้วลองใหม่")
                        time.sleep(wait_time)
                        continue
                elif "404" in error_msg or "NOT_FOUND" in error_msg:
                    print(f"[Debug] โมเดล {model_name} ไม่มีอยู่ ลองโมเดลถัดไป")
                    break
                else:
                    raise
    
    raise Exception("ลองทุกโมเดลแล้วแต่ไม่มีโมเดลไหนใช้งานได้")


# ===== คำสั่งแบบ Prefix =====

@bot.command(name="chat", help="คุยเล่นกับบอท")
async def chat_command(ctx: commands.Context, *, message: str):
    print(f"[Debug] !chat ถูกเรียกใช้ โดย {ctx.author} ข้อความ: {message}")
    try:
        async with ctx.typing():
            answer = await ask_gemini(message)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัดเนื่องจากยาวเกิน)"
            await ctx.send(answer)
    except Exception as e:
        await ctx.send(f"เกิดข้อผิดพลาด: {e}")


@bot.command(name="ask", help="ถามความรู้ทั่วไป แบบบล็อกโค้ด")
async def ask_command(ctx: commands.Context, *, question: str):
    print(f"[Debug] !ask ถูกเรียกใช้ โดย {ctx.author} คำถาม: {question}")
    try:
        async with ctx.typing():
            answer = await ask_gemini(question)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัดเนื่องจากยาวเกิน)"
            await ctx.send(f"```\n{answer}\n```")
    except Exception as e:
        await ctx.send(f"เกิดข้อผิดพลาด: {e}")


# ===== Slash Command =====

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


# ===== Event: ตอบอัตโนมัติในห้อง AI + ตอบเมื่อถูกแท็ก =====

@bot.event
async def on_message(message: discord.Message):
    # ข้ามข้อความของบอทเอง (สำคัญมาก กัน infinite loop)
    if message.author == bot.user:
        return

    # ข้ามข้อความของบอทอื่น
    if message.author.bot:
        return

    # ข้ามข้อความที่เป็นคำสั่ง !chat, !ask, /chat, /ask
    content_lower = message.content.lower()
    if content_lower.startswith(("!chat", "!ask", "/chat", "/ask")):
        await bot.process_commands(message)
        return

    # ข้ามข้อความที่แท็ก @everyone หรือ @here
    if message.mentions and any(m in (discord.Object(id=0),) for m in message.mentions):
        return
    if "@everyone" in message.content or "@here" in message.content:
        return

    # ข้ามข้อความว่าง
    if not message.content.strip():
        return

    # ตรวจสอบว่าเป็นห้อง AI ไหม
    is_ai_channel = (AI_CHANNEL_ID is not None and message.channel.id == AI_CHANNEL_ID)
    
    # หรือถูกแท็ก
    is_mentioned = bot.user in message.mentions

    if not (is_ai_channel or is_mentioned):
        return

    # เตรียมข้อความ (ลบแท็กออกถ้ามี)
    content = message.content
    if is_mentioned:
        content = content.replace(f"<@{bot.user.id}>", "").strip()
    
    # ถ้าข้อความว่างหลังลบแท็ก ให้ข้าม
    if not content:
        return

    print(f"[Debug] {'ห้อง AI' if is_ai_channel else 'ถูกแท็ก'} โดย {message.author}: {content}")

    try:
        async with message.channel.typing():
            answer = await ask_gemini(content)
            if len(answer) > 1990:
                answer = answer[:1990] + "\n...(ข้อความถูกตัดเนื่องจากยาวเกิน)"
            
            # ในห้อง AI ตอบปกติ, ในห้องอื่น reply
            if is_ai_channel:
                await message.channel.send(answer)
            else:
                await message.reply(answer)
            
            print(f"[Debug] ตอบสำเร็จ ความยาว {len(answer)} ตัวอักษร")
    except Exception as e:
        print(f"[Debug] เกิดข้อผิดพลาด: {e}")
        await message.channel.send(f"เกิดข้อผิดพลาด: {e}")

    await bot.process_commands(message)


bot.run(DISCORD_TOKEN)
