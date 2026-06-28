import asyncio, sqlite3, os, logging, json, re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
import google.generativeai as genai

load_dotenv()
_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_gemini_key = os.environ.get("GEMINI_API_KEY", "")
DB_PATH = Path("reminders.db")
if not _bot_token: raise SystemExit("missing TELEGRAM_BOT_TOKEN")
if not _gemini_key: raise SystemExit("missing GEMINI_API_KEY")

genai.configure(api_key=_gemini_key)
model = genai.GenerativeModel("gemini-2.0-flash-001")
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

DEFAULT_TZ = ZoneInfo("Asia/Kolkata")
IST = DEFAULT_TZ

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER UNIQUE NOT NULL,
            name TEXT NOT NULL,
            timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
            morning_brief_enabled INTEGER DEFAULT 1,
            morning_brief_time TEXT DEFAULT '08:00',
            last_brief_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            remind_at TIMESTAMP NOT NULL,
            is_sent INTEGER DEFAULT 0,
            recurrence TEXT,
            event_datetime TIMESTAMP,
            reminder_offset INTEGER,
            task_title TEXT,
            recurrence_rule TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_reminders_unsent
            ON reminders(is_sent, remind_at);
        CREATE TABLE IF NOT EXISTS fired_instances (
            reminder_id INTEGER NOT NULL,
            scheduled_at TEXT NOT NULL,
            PRIMARY KEY (reminder_id, scheduled_at)
        );
    """)
    conn.commit()
    # Safe migration for existing databases
    cols = [r[1] for r in conn.execute("PRAGMA table_info(reminders)").fetchall()]
    migs = {"event_datetime": "TIMESTAMP", "reminder_offset": "INTEGER",
            "task_title": "TEXT", "recurrence_rule": "TEXT"}
    for name, typ in migs.items():
        if name not in cols:
            conn.execute("ALTER TABLE reminders ADD COLUMN " + name + " " + typ)
    ucols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    umigs = {"morning_brief_enabled": "INTEGER DEFAULT 1",
             "morning_brief_time": "TEXT DEFAULT '08:00'",
             "last_brief_date": "TEXT"}
    for name, typ in umigs.items():
        if name not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN " + name + " " + typ)
    conn.commit(); conn.close()
    log.info("Database initialized")

def fmt_ist(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%a %b %d, %I:%M %p IST")

MOTIVATION_LINES = [
    "Keep going, you are doing great!",
    "Small steps lead to big results.",
    "Stay focused and stay awesome.",
    "You have got this!",
    "Make today count.",
    "Progress over perfection.",
    "One step at a time.",
    "You are unstoppable!",
    "Every day is a fresh start.",
    "Believe you can and you are halfway there.",
]

PREFIXES = [
    "remind me to ", "remind me ", "please remind me to ", "please remind me ",
    "can you remind me to ", "can you remind me ", "could you remind me to ",
    "could you remind me ", "i need to be reminded to ",
]

DAY_MAP = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
           "friday": 4, "saturday": 5, "sunday": 6}

OFFSET_PATTERN = re.compile(
    r"remind me (?:at|for|in|about) "
    r"((?:\d+\s*(?:min(?:ute)?s?|hour(?:s)?|day(?:s)?|h|m)\s*)+)",
    re.IGNORECASE
)

def parse_with_gemini(text):
    if not _gemini_key:
        return None
    try:
        now = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
        prompt = "Current time: " + now + "\n"
        prompt += "Parse into JSON: " + str(text)[:500] + "\n"
        prompt += "Fields: message, datetime (ISO 8601), recurrence (null/daily/weekdays/weekly)\n"
        prompt += "Return ONLY valid JSON, no markdown\n"
        resp = model.generate_content(prompt)
        txt = resp.text.strip()
        triq = chr(34) * 3
        if txt.startswith(triq):
            parts = txt.split("\n", 1)
            if len(parts) > 1:
                txt = parts[1].rsplit(triq, 1)[0].strip()
        elif txt.startswith("```"):
            parts = txt.split("\n", 1)
            if len(parts) > 1:
                txt = parts[1].rsplit("```", 1)[0].strip()
        return json.loads(txt)
    except Exception as e:
        log.warning("Gemini parse failed: %s", e)
        return None

def parse_reminder(text):
    result = parse_with_gemini(text)
    if result and result.get("datetime"):
        return result
    log.info("Gemini failed, trying dateparser")
    try:
        import dateparser
        from dateparser.search import search_dates
    except ImportError:
        return None
    settings = {"TIMEZONE": "Asia/Kolkata", "RETURN_AS_TIMEZONE_AWARE": True}
    try:
        results = search_dates(text, languages=["en"], settings=settings)
    except:
        results = None
    if results:
        msg_part, dt = results[0]
        msg = text.replace(msg_part, "", 1).strip()
        if not msg:
            msg = text
        msg = msg.strip(" ,;:!?")
        if not msg:
            msg = text
        return {"message": msg[:200], "datetime": dt.isoformat(), "recurrence": None}
    try:
        dt = dateparser.parse(text, settings=settings)
        if dt:
            return {"message": text[:200], "datetime": dt.isoformat(), "recurrence": None}
    except:
        pass
    return None

def clean_title(text):
    t = text.strip()
    for p in PREFIXES:
        if t.lower().startswith(p):
            t = t[len(p):]
            break
    t = t.strip(" ,;:!?.").strip()
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t

def parse_dual_time(text):
    """Extract event_time + reminder_time from dual-time patterns."""
    import dateparser
    dp_settings = {"TIMEZONE": "Asia/Kolkata", "RETURN_AS_TIMEZONE_AWARE": True}
    lower = text.lower()
    offset_match = OFFSET_PATTERN.search(lower)
    if offset_match:
        offset_str = offset_match.group(1)
        total_seconds = 0
        for num, unit in re.findall(r"(\d+)\s*(min(?:ute)?s?|hour(?:s)?|day(?:s)?|h|m)", offset_str, re.IGNORECASE):
            n = int(num)
            u = unit.lower().rstrip("s")
            if u in ("min", "minute", "m"):
                total_seconds += n * 60
            elif u in ("hour", "h"):
                total_seconds += n * 3600
            elif u in ("day",):
                total_seconds += n * 86400
        before = text[:offset_match.start()].strip().rstrip(",.")
        if before:
            if "." in before:
                sentences = [s.strip() for s in before.replace("!", ".").replace("?", ".").split(".") if s.strip()]
                event_text = sentences[-1] if sentences else before
            else:
                event_text = before
        else:
            event_text = text.replace(offset_match.group(0), "").strip()
        event_dt = dateparser.parse(event_text, settings=dp_settings)
        if event_dt:
            reminder_dt = event_dt - timedelta(seconds=total_seconds)
            title = clean_title(event_text)
            if not title:
                title = clean_title(text.replace(offset_match.group(0), "").strip())
            return {
                "task_title": title[:200],
                "event_datetime": event_dt.isoformat(),
                "reminder_datetime": reminder_dt.isoformat(),
                "reminder_offset": total_seconds,
                "recurrence": None,
                "recurrence_rule": None,
            }
    seg_match = re.split(r"[.!?]\s*(?=remind me\b)", text, maxsplit=1, flags=re.IGNORECASE)
    if len(seg_match) == 2:
        event_seg, remind_seg = seg_match[0].strip(), seg_match[1].strip()
        if event_seg and remind_seg:
            event_dt = dateparser.parse(event_seg, settings=dp_settings)
            remind_dt = dateparser.parse(remind_seg, settings=dp_settings)
            if event_dt and remind_dt:
                title = clean_title(event_seg)
                return {
                    "task_title": title[:200],
                    "event_datetime": event_dt.isoformat(),
                    "reminder_datetime": remind_dt.isoformat(),
                    "reminder_offset": None,
                    "recurrence": None,
                    "recurrence_rule": None,
                }
    return None

def parse_recurrence(text):
    """Extract recurrence rule from text. Returns dict or None."""
    lower = text.lower()
    m = re.search(r"every\s+(\d+)\s*(hour|hr|day|d)(?:s)?\b", lower, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit in ("hour", "hr"):
            return {"type": "interval", "hours": n}
        else:
            return {"type": "interval", "days": n}
    m = re.search(r"every\s+month\s+on\s+the\s+(\d+)\w{2}\b", lower, re.IGNORECASE)
    if m:
        return {"type": "monthly", "day": int(m.group(1))}
    if re.search(r"every\s+year\b", lower):
        return {"type": "yearly"}
    day_names = "|".join(DAY_MAP.keys())
    m = re.search(r"every\s+(" + day_names + r")\b", lower, re.IGNORECASE)
    if m:
        return {"type": "weekly", "days": [DAY_MAP[m.group(1).lower()]]}
    if re.search(r"every\s+weekday\b", lower):
        return {"type": "weekly", "days": [0, 1, 2, 3, 4]}
    if re.search(r"every\s+weekend\b", lower):
        return {"type": "weekly", "days": [5, 6]}
    if re.search(r"every\s+day\b", lower):
        return {"type": "daily"}
    return None

def parse_reminder_extended(text):
    """Extended parser: dual-time, recurrence, then fallback to basic."""
    dual = parse_dual_time(text)
    if dual:
        rec = parse_recurrence(text)
        if rec:
            dual["recurrence_rule"] = json.dumps(rec)
            dual["recurrence"] = rec.get("type")
        return dual
    basic = parse_reminder(text)
    if not basic:
        return None
    rec = parse_recurrence(text)
    if rec:
        basic["recurrence_rule"] = json.dumps(rec)
        basic["recurrence"] = rec.get("type")
    raw_msg = basic.get("message", "")
    basic["task_title"] = clean_title(raw_msg)
    return basic

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    cid = update.effective_chat.id
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (user_id, chat_id, name) VALUES (?,?,?)", (u.id, cid, u.full_name or ""))
    conn.commit(); conn.close()
    msg = "Hello " + u.first_name + "!\n\n"
    msg += "/add <msg> - Set a reminder (e.g. \"Buy milk tomorrow at 5pm\")\n"
    msg += "/reminders - List all pending reminders\n"
    msg += "/today - See what's due today\n"
    msg += "/week - See what's due this week\n"
    msg += "/complete <id> - Mark a reminder as done\n"
    msg += "/cancel <id> - Delete a reminder\n"
    msg += "/stop <id> - Stop a recurring series\n"
    msg += "/delete <id> - Delete a reminder\n"
    msg += "/brief - Toggle morning brief on/off"
    await update.message.reply_text(msg)

async def add_reminder(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("Usage: /add <message>"); return
    txt = " ".join(ctx.args)
    u = update.effective_user; cid = update.effective_chat.id
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (user_id, chat_id, name) VALUES (?,?,?)", (u.id, cid, u.full_name or ""))
    conn.commit()
    parsed = parse_reminder_extended(txt)
    if not parsed or not (parsed.get("reminder_datetime") or parsed.get("datetime")):
        await update.message.reply_text("Could not understand when."); conn.close(); return
    try:
        ra_str = parsed.get("reminder_datetime") or parsed.get("datetime")
        ra = datetime.fromisoformat(ra_str)
        if ra.tzinfo is None: ra = ra.replace(tzinfo=IST)
        ra_utc = ra.astimezone(timezone.utc)
    except:
        await update.message.reply_text("Could not parse the time."); conn.close(); return
    task = parsed.get("task_title") or parsed.get("message", txt)[:200]
    msg = parsed.get("message", txt)[:200]
    rec = parsed.get("recurrence")
    rec_rule = parsed.get("recurrence_rule")

    # ── DEBUG: log raw state before any fix ──
    log.info("===== SCHEDULER DEBUG =====")
    log.info("User text: %s", txt)
    log.info("Current local (UTC): %s", datetime.now(timezone.utc).isoformat())
    log.info("Parsed recurrence: %s", rec)
    log.info("Parsed recurrence_rule: %s", rec_rule)
    log.info("Parsed remind_at (ra_utc): %s", ra_utc.isoformat())

    # ── Scheduling-layer fallback: detect interval patterns in raw text
    #     when parse_recurrence missed them (e.g. "every N minutes"). ──
    if not rec_rule and not rec:
        lower = txt.lower()
        m = re.search(r"every\s+(\d+)\s*(min|minute|hour|hr)(?:s)?\b", lower)
        if m:
            n = int(m.group(1))
            unit = m.group(2).lower()
            if unit in ("min", "minute"):
                interval_rule = {"type": "interval", "minutes": n}
            else:
                interval_rule = {"type": "interval", "hours": n}
            rec_rule = json.dumps(interval_rule)
            rec = "interval"
            log.info(
                "Scheduling-layer fallback: detected interval rule=%s",
                rec_rule
            )
    # ── End fallback ──

    # ── DEBUG: state after fallback ──
    log.info("After fallback - rec: %s rec_rule: %s", rec, rec_rule)

    # ── Fix: For interval recurrence, compute first fire as now + interval ──
    if rec_rule:
        try:
            rr = json.loads(rec_rule) if isinstance(rec_rule, str) else rec_rule
            log.info("Recurrence rule (parsed): type=%s", rr.get("type"))
            if rr.get("type") == "interval":
                now_utc = datetime.now(timezone.utc)
                interval_delta = timedelta(
                    hours=rr.get("hours", 0),
                    minutes=rr.get("minutes", 0),
                    days=rr.get("days", 0)
                )
                log.info("Interval delta: %s", interval_delta)
                log.info("Delta total seconds: %s", interval_delta.total_seconds())
                if interval_delta.total_seconds() > 0:
                    first_run = now_utc + interval_delta
                    log.info("Computed first_run (now + delta): %s", first_run.isoformat())
                    log.info("Original parsed ra_utc: %s", ra_utc.isoformat())
                    ra_utc = first_run
                    ra = ra_utc.astimezone(IST)
                    log.info("OVERRIDDEN ra_utc -> %s", ra_utc.isoformat())
                else:
                    log.info("Delta is zero or negative, NOT overriding ra_utc")
            else:
                log.info("Type is %s, not 'interval' — leaving ra_utc unchanged", rr.get("type"))
        except Exception as e:
            log.warning("Interval start-time fix failed: %s", e)
    else:
        log.info("No rec_rule — leaving ra_utc unchanged at %s", ra_utc.isoformat())
    # ── End fix ──

    # ── DEBUG: final values before DB write ──
    log.info("FINAL remind_at written to DB: %s", ra_utc.isoformat())
    event_dt = parsed.get("event_datetime")
    offset = parsed.get("reminder_offset")
    cur = conn.execute(
        "INSERT INTO reminders (user_id, chat_id, message, remind_at, recurrence, recurrence_rule, event_datetime, reminder_offset, task_title) VALUES (?,?,?,?,?,?,?,?,?)",
        (u.id, cid, msg, ra_utc.isoformat(), rec, rec_rule, event_dt, offset, task)
    )
    rid = cur.lastrowid; conn.commit(); conn.close()
    if ctx.job_queue:
        ctx.job_queue.run_once(send_reminder_callback, when=ra_utc, data={"rid": rid, "c": cid}, name="r"+str(rid))
        # ── DEBUG: what APScheduler receives ──
        log.info("APScheduler run_once(when=%s, name=r%s)", ra_utc.isoformat(), rid)
    ra_ist = ra_utc.astimezone(IST)
    reply = "\u2705 " + task + "\n\u23f0 " + fmt_ist(ra_ist)
    if rec: reply += "\n\U0001f504 Recurring: " + rec
    if event_dt:
        ev = datetime.fromisoformat(event_dt)
        if ev.tzinfo is None: ev = ev.replace(tzinfo=timezone.utc)
        reply += "\n\U0001f4c5 Event: " + fmt_ist(ev)
    await update.message.reply_text(reply)

async def list_reminders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    rows = get_db().execute(
        "SELECT id, message, remind_at, recurrence, task_title FROM reminders WHERE user_id=? AND is_sent=0 ORDER BY remind_at",
        (uid,)
    ).fetchall()
    if not rows: await update.message.reply_text("No pending reminders!"); return
    out = ["Your Reminders:"]
    for r in rows:
        d = datetime.fromisoformat(r["remind_at"])
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        d_ist = d.astimezone(IST)
        title = r["task_title"] or r["message"][:50]
        line = "#" + str(r["id"]) + " " + title + " " + fmt_ist(d_ist)
        if r["recurrence"]: line += " Recurring: " + r["recurrence"]
        out.append(line)
    await update.message.reply_text("\n".join(out))

async def today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = datetime.now(timezone.utc); eod = n.replace(hour=23, minute=59, second=59)
    uid = update.effective_user.id
    rows = get_db().execute(
        "SELECT id,message,remind_at,task_title FROM reminders WHERE user_id=? AND is_sent=0 AND remind_at BETWEEN ? AND ? ORDER BY remind_at",
        (uid, n.isoformat(), eod.isoformat())
    ).fetchall()
    if not rows: await update.message.reply_text("Nothing due today!"); return
    out = ["Due Today:"]
    for r in rows:
        d = datetime.fromisoformat(r["remind_at"])
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        d_ist = d.astimezone(IST)
        title = r["task_title"] or r["message"][:50]
        out.append("#" + str(r["id"]) + " " + title + " " + fmt_ist(d_ist))
    await update.message.reply_text("\n".join(out))

async def week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = datetime.now(timezone.utc); eow = n + timedelta(days=7)
    uid = update.effective_user.id
    rows = get_db().execute(
        "SELECT id,message,remind_at,task_title FROM reminders WHERE user_id=? AND is_sent=0 AND remind_at BETWEEN ? AND ? ORDER BY remind_at",
        (uid, n.isoformat(), eow.isoformat())
    ).fetchall()
    if not rows: await update.message.reply_text("Nothing due this week!"); return
    out = ["This Week:"]
    for r in rows:
        d = datetime.fromisoformat(r["remind_at"])
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        d_ist = d.astimezone(IST)
        title = r["task_title"] or r["message"][:50]
        out.append("#" + str(r["id"]) + " " + title + " " + fmt_ist(d_ist))
    await update.message.reply_text("\n".join(out))

async def complete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("Usage: /complete <id>"); return
    try: rid = int(ctx.args[0])
    except: await update.message.reply_text("Invalid ID."); return
    uid = update.effective_user.id
    cur = get_db().execute("UPDATE reminders SET is_sent=1 WHERE id=? AND user_id=?", (rid, uid))
    cur.connection.commit(); cur.connection.close()
    if cur.rowcount: await update.message.reply_text("Done #" + str(rid) + "!")
    else: await update.message.reply_text("Not found.")

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("Usage: /cancel <id>"); return
    try: rid = int(ctx.args[0])
    except: await update.message.reply_text("Invalid ID."); return
    uid = update.effective_user.id
    cur = get_db().execute("DELETE FROM reminders WHERE id=? AND user_id=?", (rid, uid))
    cur.connection.commit(); cur.connection.close()
    if cur.rowcount: await update.message.reply_text("Cancelled #" + str(rid) + ".")
    else: await update.message.reply_text("Not found.")

async def stop_recurring(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: await update.message.reply_text("Usage: /stop <id>"); return
    try: rid = int(ctx.args[0])
    except: await update.message.reply_text("Invalid ID."); return
    uid = update.effective_user.id
    conn = get_db()
    row = conn.execute("SELECT * FROM reminders WHERE id=? AND user_id=?", (rid, uid)).fetchone()
    if not row: conn.close(); await update.message.reply_text("Not found."); return
    if not row["recurrence"] and not row["recurrence_rule"]:
        conn.close(); await update.message.reply_text("Not a recurring series."); return
    conn.execute("UPDATE reminders SET recurrence=NULL, recurrence_rule=NULL WHERE id=?", (rid,))
    conn.commit(); conn.close()
    if ctx.job_queue:
        for j in ctx.job_queue.get_jobs_by_name("r"+str(rid)):
            j.schedule_removal()
    await update.message.reply_text(
        "Stopped recurring series #" + str(rid) + ". No further reminders will fire."
    )

async def toggle_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db()
    row = conn.execute("SELECT morning_brief_enabled FROM users WHERE user_id=?", (uid,)).fetchone()
    if not row:
        await update.message.reply_text("Please /start first."); conn.close(); return
    val = 0 if row["morning_brief_enabled"] else 1
    conn.execute("UPDATE users SET morning_brief_enabled=? WHERE user_id=?", (val, uid))
    conn.commit(); conn.close()
    if val:
        await update.message.reply_text("Morning brief enabled. You will receive it daily at 8 AM IST.")
    else:
        await update.message.reply_text("Morning brief disabled.")

async def send_reminder_callback(ctx: ContextTypes.DEFAULT_TYPE):
    d = ctx.job.data; rid = d.get("rid"); cid = d.get("c")
    conn = get_db()
    row = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
    if not row or row["is_sent"]: conn.close(); return
    try:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Done", callback_data="d"+str(rid)),
             InlineKeyboardButton("Snooze 5m", callback_data="s"+str(rid))]
        ])
        dt = datetime.fromisoformat(row["remind_at"])
        if dt.tzinfo: dt_ist = dt.astimezone(IST)
        else: dt_ist = dt.replace(tzinfo=timezone.utc).astimezone(IST)
        title = row["task_title"] or row["message"]
        msg = "Reminder!\n\n" + title + "\n\u23f0 " + fmt_ist(dt_ist)
        await ctx.bot.send_message(chat_id=cid, text=msg, reply_markup=kb)
        log.info("Sent #%d", rid)
    except Exception as e:
        log.error("Send #%d failed: %s", rid, e); conn.close(); return
    rec = row["recurrence"]
    rec_rule_str = row["recurrence_rule"]
    rec_rule = None
    if rec_rule_str:
        try:
            rec_rule = json.loads(rec_rule_str)
        except:
            rec_rule = None
    base_dt = datetime.fromisoformat(row["remind_at"])
    if base_dt.tzinfo is None:
        base_dt = base_dt.replace(tzinfo=timezone.utc)
    # Mark this instance as fired (duplicate prevention)
    conn.execute(
        "INSERT OR IGNORE INTO fired_instances (reminder_id, scheduled_at) VALUES (?,?)",
        (rid, base_dt.isoformat())
    )
    conn.commit()
    next_dt = None
    if rec_rule:
        rtype = rec_rule.get("type")
        if rtype == "daily":
            next_dt = base_dt + timedelta(days=1)
        elif rtype == "weekly":
            days = rec_rule.get("days", [])
            if days:
                for shift in range(1, 8):
                    candidate = base_dt + timedelta(days=shift)
                    if candidate.weekday() in days:
                        next_dt = candidate.replace(hour=base_dt.hour, minute=base_dt.minute, second=0, microsecond=0)
                        break
        elif rtype == "monthly":
            day = rec_rule.get("day", 1)
            m = base_dt.month + 1
            y = base_dt.year
            if m > 12:
                m = 1; y += 1
            import calendar
            maxd = calendar.monthrange(y, m)[1]
            target_day = min(day, maxd)
            next_dt = base_dt.replace(year=y, month=m, day=target_day, hour=base_dt.hour, minute=base_dt.minute, second=0, microsecond=0)
        elif rtype == "yearly":
            next_dt = base_dt.replace(year=base_dt.year + 1)
        elif rtype == "interval":
            hours = rec_rule.get("hours")
            minutes = rec_rule.get("minutes")
            days = rec_rule.get("days")
            if hours:
                next_dt = base_dt + timedelta(hours=hours)
            elif minutes:
                next_dt = base_dt + timedelta(minutes=minutes)
            elif days:
                next_dt = base_dt + timedelta(days=days)
    elif rec == "daily":
        next_dt = base_dt + timedelta(days=1)
    elif rec == "weekdays":
        next_dt = base_dt + timedelta(days=1)
        while next_dt.weekday() >= 5:
            next_dt += timedelta(days=1)
    elif rec == "weekly":
        next_dt = base_dt + timedelta(days=7)
    if next_dt and next_dt > datetime.now(timezone.utc):
        conn.execute("UPDATE reminders SET remind_at=? WHERE id=?", (next_dt.isoformat(), rid))
        if ctx.job_queue:
            ctx.job_queue.run_once(send_reminder_callback, when=next_dt,
                                   data={"rid": rid, "c": cid}, name="r"+str(rid))
        log.info("Recurrence #%d next at %s", rid, next_dt.isoformat())
    else:
        conn.execute("UPDATE reminders SET is_sent=1 WHERE id=?", (rid,))
    conn.commit(); conn.close()

async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    rid = int(q.data[1:])
    if q.data.startswith("d"):
        uid = update.effective_user.id
        cur = get_db().execute("UPDATE reminders SET is_sent=1 WHERE id=? AND user_id=?", (rid, uid))
        cur.connection.commit(); cur.connection.close()
        await q.edit_message_text(q.message.text + "\n(Completed)")
    elif q.data.startswith("s"):
        conn = get_db()
        row = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
        if row:
            nt = datetime.now(timezone.utc) + timedelta(minutes=5)
            conn.execute("UPDATE reminders SET remind_at=? WHERE id=?", (nt.isoformat(), rid))
            conn.commit()
            ctx.job_queue.run_once(send_reminder_callback, when=nt,
                                   data={"rid": rid, "c": row["chat_id"]}, name="r"+str(rid))
            await q.edit_message_text(q.message.text + "\n(Snoozed 5m)")
        conn.close()

async def error_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    log.error("Update %s caused error %s", update, ctx.error)

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown. Try /help")

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await start(update, ctx)

async def send_morning_brief(ctx: ContextTypes.DEFAULT_TYPE):
    """Send daily morning brief to all users who have it enabled."""
    conn = get_db()
    users = conn.execute("SELECT * FROM users WHERE morning_brief_enabled=1").fetchall()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59)
    tomorrow_end = today_start + timedelta(days=2)
    today_str = datetime.now(IST).strftime("%A, %b %d, %Y")
    import random
    for u in users:
        uid = u["user_id"]
        last = u["last_brief_date"]
        if last and last == today_start.date().isoformat():
            continue
        today_rem = conn.execute(
            "SELECT id, message, remind_at, task_title, recurrence FROM reminders WHERE user_id=? AND is_sent=0 AND remind_at BETWEEN ? AND ? ORDER BY remind_at",
            (uid, today_start.isoformat(), today_end.isoformat())
        ).fetchall()
        next24 = conn.execute(
            "SELECT id, message, remind_at, task_title, recurrence FROM reminders WHERE user_id=? AND is_sent=0 AND remind_at BETWEEN ? AND ? AND (remind_at < ? OR remind_at > ?) ORDER BY remind_at",
            (uid, today_start.isoformat(), tomorrow_end.isoformat(), today_start.isoformat(), today_end.isoformat())
        ).fetchall()
        lines = []
        lines.append("\U0001f305 Good Morning " + u["name"].split()[0] + "! \U0001f4c5 " + today_str)
        lines.append("")
        if today_rem:
            lines.append("\U0001f4cc Reminders Today:")
            for r in today_rem:
                d = datetime.fromisoformat(r["remind_at"])
                if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
                d_ist = d.astimezone(IST)
                title = r["task_title"] or r["message"][:50]
                lines.append("#" + str(r["id"]) + " " + title + " - " + d_ist.strftime("%I:%M %p IST"))
        else:
            lines.append("No reminders for today. Enjoy your day!")
        lines.append("")
        if next24:
            lines.append("\u26a0\ufe0f Reminders in the next 24 hours:")
            for r in next24:
                d = datetime.fromisoformat(r["remind_at"])
                if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
                d_ist = d.astimezone(IST)
                title = r["task_title"] or r["message"][:50]
                lines.append("#" + str(r["id"]) + " " + title + " - " + d_ist.strftime("%I:%M %p IST"))
            lines.append("")
        total_today = len(today_rem)
        pending = conn.execute("SELECT COUNT(*) FROM reminders WHERE user_id=? AND is_sent=0", (uid,)).fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM reminders WHERE user_id=? AND is_sent=1", (uid,)).fetchone()[0]
        lines.append(
            "\U0001f4ca Summary: " + str(total_today) + " today, "
            + str(pending) + " pending, " + str(completed) + " completed"
        )
        lines.append("")
        lines.append(random.choice(MOTIVATION_LINES))
        try:
            await ctx.bot.send_message(chat_id=u["chat_id"], text="\n".join(lines))
            conn.execute("UPDATE users SET last_brief_date=? WHERE user_id=?", (today_start.date().isoformat(), uid))
            conn.commit()
            log.info("Morning brief sent to user %d", uid)
        except Exception as e:
            log.warning("Morning brief failed for %d: %s", uid, e)
    conn.close()

async def recover_missed(app):
    n = datetime.now(timezone.utc)
    conn = get_db()
    missed = conn.execute("SELECT * FROM reminders WHERE is_sent=0 AND remind_at <= ? ORDER BY remind_at", (n.isoformat(),)).fetchall()
    if missed:
        log.info("Recovering %d missed", len(missed))
        for row in missed:
            try:
                await app.bot.send_message(chat_id=row["chat_id"],
                    text="Reminder!\n(missed)\n\n" + row["message"])
            except: pass
            rec = row["recurrence"]
            rec_rule_str = row["recurrence_rule"]
            if rec_rule_str:
                try: rec_rule = json.loads(rec_rule_str)
                except: rec_rule = None
                base = datetime.fromisoformat(row["remind_at"])
                if base.tzinfo is None: base = base.replace(tzinfo=timezone.utc)
                next_dt = base
                while next_dt <= n:
                    rtype = rec_rule.get("type") if rec_rule else None
                    if rtype == "daily":
                        next_dt += timedelta(days=1)
                    elif rtype == "weekly":
                        days = rec_rule.get("days", [])
                        if days:
                            for _ in range(7):
                                next_dt += timedelta(days=1)
                                if next_dt.weekday() in days: break
                            else: next_dt += timedelta(days=1)
                    elif rtype == "monthly":
                        next_dt = next_dt.replace(month=next_dt.month + 1)
                        if next_dt.month > 12:
                            next_dt = next_dt.replace(year=next_dt.year + 1, month=1)
                    elif rtype == "yearly":
                        next_dt = next_dt.replace(year=next_dt.year + 1)
                    elif rtype == "interval":
                        hours = rec_rule.get("hours")
                        minutes = rec_rule.get("minutes")
                        days = rec_rule.get("days")
                        if hours: next_dt += timedelta(hours=hours)
                        elif minutes: next_dt += timedelta(minutes=minutes)
                        elif days: next_dt += timedelta(days=days)
                    else: break
                if next_dt > n:
                    conn.execute("UPDATE reminders SET remind_at=? WHERE id=?", (next_dt.isoformat(), row["id"]))
                    app.job_queue.run_once(send_reminder_callback, when=next_dt,
                                           data={"rid": row["id"], "c": row["chat_id"]}, name="r"+str(row["id"]))
                else:
                    conn.execute("UPDATE reminders SET is_sent=1 WHERE id=?", (row["id"],))
            elif rec in ("daily", "weekdays"):
                base = datetime.fromisoformat(row["remind_at"])
                delta = timedelta(days=1) if rec in ("daily","weekdays") else timedelta(days=7)
                nt = n.replace(hour=base.hour, minute=base.minute) + delta
                if rec == "weekdays":
                    while nt.weekday() >= 5: nt += timedelta(days=1)
                conn.execute("UPDATE reminders SET remind_at=? WHERE id=?", (nt.isoformat(), row["id"]))
                app.job_queue.run_once(send_reminder_callback, when=nt,
                                       data={"rid": row["id"], "c": row["chat_id"]}, name="r"+str(row["id"]))
            else:
                conn.execute("UPDATE reminders SET is_sent=1 WHERE id=?", (row["id"],))
        conn.commit()
    conn.close()

async def periodic_check(app):
    while True:
        await asyncio.sleep(30)
        try:
            n = datetime.now(timezone.utc)
            conn = get_db()
            due = conn.execute("SELECT * FROM reminders WHERE is_sent=0 AND remind_at <= ?", (n.isoformat(),)).fetchall()
            conn.close()
            for row in due:
                if not app.job_queue.get_jobs_by_name("r"+str(row["id"])):
                    app.job_queue.run_once(send_reminder_callback, when=0,
                                           data={"rid": row["id"], "c": row["chat_id"]}, name="r"+str(row["id"]))
        except: pass

async def schedule_morning_briefs(app):
    """Schedule morning briefs for all users. Runs daily at each user's morning_brief_time."""
    conn = get_db()
    users = conn.execute("SELECT * FROM users WHERE morning_brief_enabled=1").fetchall()
    conn.close()
    for u in users:
        brief_time = u["morning_brief_time"] or "08:00"
        hour, minute = (int(x) for x in brief_time.split(":"))
        now_ist = datetime.now(IST)
        target = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now_ist:
            target += timedelta(days=1)
        target_utc = target.astimezone(timezone.utc)
        jname = "mb_" + str(u["user_id"])
        if not app.job_queue.get_jobs_by_name(jname):
            app.job_queue.run_daily(send_morning_brief, time=target_utc.timetz(), name=jname)
            log.info("Morning brief scheduled for user %d at %s", u["user_id"], brief_time)

async def post_init(app):
    log.info("Starting up...")
    await recover_missed(app)
    await schedule_morning_briefs(app)
    asyncio.create_task(periodic_check(app))

def main():
    init_db()
    app = Application.builder().token(_bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("add", add_reminder))
    app.add_handler(CommandHandler("reminders", list_reminders))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("complete", complete))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("delete", cancel))
    app.add_handler(CommandHandler("stop", stop_recurring))
    app.add_handler(CommandHandler("brief", toggle_brief))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback, pattern=r"^(d[0-9]|s[0-9])"))
    app.add_error_handler(error_handler)
    log.info("Started polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
