import os
import sys
import time
import asyncio
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
import discord
from discord import app_commands
from discord.ext import commands
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")   # ไม่บังคับ: มีแล้วค้นเว็บทั่วไปแม่นขึ้น
AI_CHANNEL_ID = os.getenv("AI_CHANNEL_ID")

if not DISCORD_TOKEN or not OPENROUTER_API_KEY:
    print("[ข้อผิดพลาด] ไม่พบ DISCORD_TOKEN หรือ OPENROUTER_API_KEY")
    sys.exit(1)

AI_CHANNEL_ID = int(AI_CHANNEL_ID) if AI_CHANNEL_ID else None

client = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    default_headers={"HTTP-Referer": "https://discord.com", "X-Title": "Discord AI Bot"}
)

# ---------- สถานะส่วนกลาง ----------
CURRENT_MODEL = None
FREE_LIST = []
FALLBACK = ["qwen/qwen-2.5-72b-instruct:free", "google/gemma-2-9b-it:free",
            "mistralai/mistral-7b-instruct:free", "meta-llama/llama-3.3-70b-instruct:free"]
LAST_SOURCE = "ยังไม่ได้ค้น"
SEARCH_CACHE = {}
CACHE_TTL = 600
ANSWER_CACHE = {}
ANSWER_TTL = 120

DAY_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
MONTH_TH = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]

def get_time_th():
    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    return f"วัน{DAY_TH[now.weekday()]}ที่ {now.day} {MONTH_TH[now.month-1]} พ.ศ. {now.year+543} เวลา {now.strftime('%H:%M')} น. (เวลาประเทศไทย)"

# ---------- เลือกโมเดลฟรีอัตโนมัติ ----------
async def resolve_free_model(force=False):
    global CURRENT_MODEL, FREE_LIST
    if CURRENT_MODEL and not force:
        return CURRENT_MODEL
    try:
        models = await client.models.list()
        free = [m.id for m in models.data if m.id.endswith(":free")]
        FREE_LIST = free
        prefer = ["llama-3.3-70b", "qwen-2.5-72b", "llama-3.1-70b", "gemma-2-27b", "mistral"]
        chosen = None
        for p in prefer:
            for f in free:
                if p in f:
                    chosen = f; break
            if chosen: break
        if not chosen and free:
            chosen = free[0]
        if chosen:
            CURRENT_MODEL = chosen
            print(f"[ระบบ] เลือกโมเดล: {chosen}")
            return chosen
    except Exception as e:
        print(f"[คำเตือน] ดึงโมเดลไม่สำเร็จ: {e}")
    if not CURRENT_MODEL:
        CURRENT_MODEL = FALLBACK[0]
    return CURRENT_MODEL

# ---------- แหล่งค้นหาฟรี ----------
async def search_tavily(q):
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.post("https://api.tavily.com/search",
                         json={"api_key": TAVILY_API_KEY, "query": q, "max_results": 5})
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("url", ""),
                 "content": x.get("content", "")} for x in r.json().get("results", [])]

async def search_ddg(q):
    def _run():
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as d:
            return list(d.text(q, max_results=5))
    rows = await asyncio.to_thread(_run)
    return [{"title": x.get("title", ""), "url": x.get("href", ""),
             "content": x.get("body", "")} for x in rows]

async def search_wiki(q):
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get("https://th.wikipedia.org/w/api.php", params={
            "action": "query", "generator": "search", "gsrsearch": q, "gsrlimit": 3,
            "prop": "extracts", "exintro": True, "explaintext": True, "format": "json"})
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        return [{"title": p.get("title", ""),
                 "url": "https://th.wikipedia.org/wiki/" + p.get("title", "").replace(" ", "_"),
                 "content": (p.get("extract", "") or "")[:600]} for p in pages.values()]

async def search_web(q):
    global LAST_SOURCE
    key = q.strip().lower()
    hit = SEARCH_CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        LAST_SOURCE = hit[2] + " (แคช)"
        return hit[1]
    order = []
    if TAVILY_API_KEY:
        order.append(("Tavily", search_tavily))
    order += [("DuckDuckGo", search_ddg), ("Wikipedia", search_wiki)]
    for name, fn in order:
        try:
            res = await fn(q)
            if res:
                LAST_SOURCE = name
                SEARCH_CACHE[key] = (time.time(), res, name)
                return res
        except Exception as e:
            print(f"[คำเตือน] {name}: {e}")
    LAST_SOURCE = "ไม่พบผล"
    return []

def build_context(results):
    if not results:
        return "ไม่พบผลค้นหา ให้ใช้ความรู้ทั่วไปของคุณและบอกผู้ใช้ว่าไม่พบข้อมูลล่าสุด"
    return "\n\n".join(
        f"[{i}] {r['title']}\nลิงก์: {r['url']}\nเนื้อหา: {r['content'][:500]}"
        for i, r in enumerate(results, 1))

def needs_search(q: str) -> bool:
    ql = q.lower().strip()
    direct = ["สวัสดี", "หวัดดี", "สบายดี", "ขอบคุณ", "ทดสอบ", "test",
              "วันอะไร", "กี่โมง", "เวลาเท่าไหร่", "วันนี้วัน",
              "แต่ง", "กลอน", "เพลง", "ตลก", "มุก",
              "โค้ด", "code", "คำนวณ", "คณิต", "แปล", "translate"]
    return not any(p in ql for p in direct)

# ---------- ถาม AI พร้อมวนลองเมื่อ 429 ----------
async def ask_ai(question):
    global CURRENT_MODEL
    ck = question.strip().lower()
    hit = ANSWER_CACHE.get(ck)
    if hit and time.time() - hit[0] < ANSWER_TTL:
        return hit[1]

    if needs_search(question):
        results = await search_web(question)
        print(f"[ค้น] แหล่ง: {LAST_SOURCE} จำนวน {len(results)} ผล")
        context = build_context(results)
        source_note = "ตอบโดยอิงข้อมูลอ้างอิงข้างบนเป็นหลัก ถ้าไม่พอให้บอกตรงๆ อย่าเดา"
    else:
        context = "คำถามนี้ตอบจากความรู้ของคุณโดยตรง ไม่ต้องอ้างอิงเว็บ"
        source_note = "ตอบจากความรู้ของคุณได้ทันที เป็นธรรมชาติ ไม่ต้องค้น"

    system = f"""คุณคือผู้ช่วย AI อัจฉริยะ ตอบได้ทุกเรื่อง
เวลาปัจจุบัน: {get_time_th()}
ข้อมูลอ้างอิง:
{context}

กฎ:
1. ตอบภาษาไทยสุภาพ เป็นธรรมชาติ แบบเต็มคำ ห้ามใช้อิโมจิ
2. {source_note}
3. ถ้ามีลิงก์อ้างอิงที่ใช้จริง ให้ใส่ท้ายคำตอบ
4. ถ้าถามวันเวลา ให้ตอบจากเวลาปัจจุบันทันที
5. คุยเล่น สร้างสรรค์ โค้ด คณิต แปลภาษา ให้ตอบตรงๆ อย่างมั่นใจ"""

    await resolve_free_model()
    ordered = []
    if CURRENT_MODEL:
        ordered.append(CURRENT_MODEL)
    pool = FREE_LIST if FREE_LIST else FALLBACK
    ordered += [m for m in pool if m != CURRENT_MODEL]

    last_err = None
    for i, model in enumerate(ordered[:8]):
        try:
            r = await client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": question}],
                max_tokens=1200, temperature=0.6)
            answer = r.choices[0].message.content
            CURRENT_MODEL = model
            ANSWER_CACHE[ck] = (time.time(), answer)
            print(f"[สำเร็จ] โมเดล: {model}")
            return answer
        except Exception as e:
            msg = str(e)
            last_err = e
            print(f"[คำเตือน] {model}: {msg[:120]}")
            if ("429" in msg or "rate" in msg.lower() or "Provider returned error" in msg
                    or "503" in msg or "502" in msg):
                await asyncio.sleep(1.5 + i)
                continue
            if "404" in msg or "unavailable" in msg.lower():
                continue
            raise
    raise Exception(f"ผู้ให้บริการฟรีหนาแน่นชั่วคราว ลองแล้ว {len(ordered[:8])} โมเดล: {last_err}")

# ---------- ตั้งค่าบอท ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    try:
        print(f"[ระบบ] บอท {bot.user.name} ออนไลน์")
        print(f"[ระบบ] เวลา: {get_time_th()}")
        await resolve_free_model()
        synced = await bot.tree.sync()
        print(f"[ระบบ] ซิงค์ {len(synced)} คำสั่ง พร้อมใช้งาน")
    except Exception:
        traceback.print_exc()

async def send_answer(channel, question):
    try:
        answer = await ask_ai(question)
        if len(answer) > 1990:
            answer = answer[:1990] + "\n...(ข้อความถูกตัด)"
        await channel.send(answer)
    except discord.Forbidden:
        print(f"[สิทธิ์] บอทไม่มีสิทธิ์ส่งในช่อง {channel.id} — เปิดสิทธิ์ Send Messages / View Channels ที่บทบาทบอทและสิทธิ์เฉพาะช่อง")
    except Exception as e:
        traceback.print_exc()
        try:
            await channel.send(f"เกิดข้อผิดพลาด: {e}")
        except Exception:
            pass

@bot.command(name="test")
async def test_cmd(ctx):
    await ctx.send("บอททำงานปกติ พร้อมค้นหาและตอบคำถาม")

@bot.command(name="model")
async def model_cmd(ctx):
    m = await resolve_free_model()
    await ctx.send(f"โมเดลปัจจุบัน: {m}\nโมเดลฟรีที่พบ: {len(FREE_LIST)} ตัว")

@bot.command(name="sources")
async def sources_cmd(ctx):
    have = "มี" if TAVILY_API_KEY else "ไม่มี"
    await ctx.send(f"แหล่งค้นล่าสุด: {LAST_SOURCE}\nTavily key: {have}\nลำดับค้น: Tavily (ถ้ามี) แล้ว DuckDuckGo แล้ว Wikipedia")

@bot.command(name="ai")
async def ai_cmd(ctx, *, question: str):
    await send_answer(ctx.channel, question)

@bot.command(name="chat")
async def chat_cmd(ctx, *, message: str):
    await send_answer(ctx.channel, message)

@bot.tree.command(name="ai", description="ถามผู้ช่วย AI พร้อมค้นหาข้อมูลจริง")
@app_commands.describe(question="คำถาม")
async def ai_slash(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    try:
        await interaction.followup.send(await ask_ai(question))
    except Exception as e:
        await interaction.followup.send(f"เกิดข้อผิดพลาด: {e}")

@bot.event
async def on_message(m):
    try:
        if m.author == bot.user or m.author.bot:
            return
        c = m.content.strip()
        if not c:
            return
        if c.lower().startswith(("!ai ", "!chat ", "!test", "!model", "!sources")):
            await bot.process_commands(m); return
        is_ai = AI_CHANNEL_ID and m.channel.id == AI_CHANNEL_ID
        is_tag = bot.user in m.mentions
        if not (is_ai or is_tag):
            await bot.process_commands(m); return
        if is_tag:
            c = c.replace(f"<@{bot.user.id}>", "").strip()
        if not c:
            return
        await send_answer(m.channel, c)
        await bot.process_commands(m)
    except Exception:
        traceback.print_exc()

bot.run(DISCORD_TOKEN, reconnect=True)
