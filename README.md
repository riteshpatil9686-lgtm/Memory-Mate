<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram" alt="Telegram Bot">
  <img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite" alt="SQLite">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License MIT">
  <img src="https://img.shields.io/badge/APScheduler-3.10%2B-red?style=for-the-badge" alt="APScheduler">
</p>

<h1 align="center">🧠 Memory Mate</h1>
<p align="center">
  <strong>Your intelligent Telegram reminder companion with natural language parsing and recurring schedules.</strong>
  <br>
  <em>Powered by Google Gemini 2.0 Flash + python-telegram-bot + APScheduler</em>
</p>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Objectives](#-objectives)
- [Features](#-features)
- [Architecture](#-architecture)
- [Technology Stack](#-technology-stack)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
  - [Prerequisites](#prerequisites)
  - [Setup Steps](#setup-steps)
- [Environment Variables](#-environment-variables)
- [Usage Guide](#-usage-guide)
  - [Command Reference](#command-reference)
  - [Natural Language Examples](#natural-language-examples)
- [Database Schema](#-database-schema)
- [System Workflow](#-system-workflow)
- [Scheduling System](#-scheduling-system)
- [Testing](#-testing)
- [Deployment](#-deployment)
- [Configuration](#-configuration)
- [Performance Optimizations](#-performance-optimizations)
- [Security Considerations](#-security-considerations)
- [Error Handling Strategy](#-error-handling-strategy)
- [Logging & Monitoring](#-logging--monitoring)
- [Coding Standards](#-coding-standards)
- [Contributing](#-contributing)
- [Roadmap](#-roadmap)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)
- [Credits](#-credits)

---

## 🌟 Overview

**Memory Mate** is a production-grade Telegram reminder bot that lets you create reminders using everyday language. Tell it *"Buy groceries tomorrow at 5pm"* or *"Drink water every 2 hours"* — it parses the intent intelligently and schedules the reminder with zero friction.

> **Why Memory Mate?**
> Most reminder bots require rigid command syntax or manual datetime picking. Memory Mate uses Google Gemini 2.0 Flash + `dateparser` to understand natural language, and APScheduler for reliable recurring schedules with timezone-aware datetime handling.

---

## 🎯 Objectives

1. **Zero-friction reminder creation** — Type what you'd naturally say, get a reminder
2. **Reliable recurrence** — Daily, weekly, monthly, and interval-based schedules
3. **Timezone-aware** — All times stored in UTC, displayed in Asia/Kolkata (IST)
4. **Missed reminder recovery** — Automatically reschedule missed reminders on restart
5. **Minimal stack** — Single-file bot, SQLite, no Docker, no PostgreSQL

---

## ✨ Features

| Feature | Description |
|---|---|
| **Natural Language Parsing** | Understands *"remind me to buy milk tomorrow at 5pm"*, *"meeting next Monday 3pm"* |
| **Interval Recurrence** | `every 30 minutes`, `every 2 hours`, `every 3 days` |
| **Daily Recurrence** | `every day at 8 AM`, `every morning` |
| **Weekly Recurrence** | `every Monday at 6 PM`, `every weekday` |
| **Monthly Recurrence** | `every month on the 1st at 9 AM` |
| **Yearly Recurrence** | `every year on June 15th` |
| **Event-Based Reminders** | Remind N minutes/hours before an event |
| **Dual-Time Parsing** | *"Remind me 30 min before the meeting tomorrow at 3pm"* |
| **Morning Brief** | Daily summary of today's reminders sent automatically at 8 AM IST |
| **Inline Buttons** | Done / Snooze 5 minutes on every reminder notification |
| **Missed Recovery** | Recovers and reschedules missed reminders on bot restart |
| **Periodic Safeguard** | Background check every 30 seconds for any missed due reminders |
| **Scheduling Fix** | Interval reminders fire at `now + interval`, never immediately |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Telegram Cloud                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Telegram Bot API (Long Polling)                │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
└─────────────────────────────┼──────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Memory Mate (bot.py)                            │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │  Command      │───▶│  Parse Layer     │───▶│  Scheduler Layer │  │
│  │  Handlers     │    │  (Gemini API +   │    │  (APScheduler    │  │
│  │               │    │   dateparser)    │    │   JobQueue)      │  │
│  └──────────────┘    └──────────────────┘    └────────┬─────────┘  │
│         │                                              │           │
│         ▼                                              ▼           │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Storage Layer (SQLite)                      │ │
│  │  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐  │ │
│  │  │  users       │  │  reminders       │  │ fired_instances  │  │ │
│  │  │  (profiles,  │  │  (schedules, rec)│  │  (dedup log)     │  │ │
│  │  │  preferences)│  │                  │  │                  │  │ │
│  │  └─────────────┘  └──────────────────┘  └──────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Background Processes                               │ │
│  │  ┌─────────────────────┐  ┌──────────────────────────────┐    │ │
│  │  │  recover_missed()   │  │  periodic_check()           │    │ │
│  │  │  (on startup)       │  │  (every 30s safeguard)      │    │ │
│  │  └─────────────────────┘  └──────────────────────────────┘    │ │
│  │  ┌─────────────────────┐                                       │ │
│  │  │  schedule_morning_  │                                       │ │
│  │  │  briefs()           │                                       │ │
│  │  │  (daily dispatch)   │                                       │ │
│  │  └─────────────────────┘                                       │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

| Component | Technology | Version |
|---|---|---|
| Runtime | Python 3 | 3.11.15 |
| Bot Framework | python-telegram-bot | 21.10.1 |
| NL Parser | Google Gemini 2.0 Flash | — |
| NL Fallback | dateparser | (stdlib) |
| Scheduler | APScheduler (via JobQueue) | (bundled with PTB) |
| Database | SQLite 3 | (stdlib) |
| Async I/O | asyncio / anyio | (stdlib) |
| Env Management | python-dotenv | 1.1.0 |
| Async SQL | aiosqlite | 0.20.0 |

---

## 📁 Project Structure

```
Memory-Mate/
├── bot.py                           # Main application (single-file bot)
├── launcher.py                      # Background process launcher (dev utility)
├── test_recurrence_scheduling.py    # Unit tests for scheduling fix
├── requirements.txt                 # Python dependencies
├── .gitignore                       # Git ignore patterns
├── LICENSE                          # MIT License
├── README.md                        # This file
├── reminders.db                     # SQLite database (created at runtime)
├── .env                             # Environment variables (NOT committed)
├── bot.log                          # Log file (created at runtime)
└── bot.pid                          # PID file (created by launcher)
```

### File Descriptions

| File | Purpose |
|---|---|
| `bot.py` | Single-file Telegram bot (~790 lines). Contains all handlers, parsing, scheduling, database operations, and background tasks. |
| `launcher.py` | Utility script that starts `bot.py` as a background process and writes its PID. Used for development/testing. |
| `test_recurrence_scheduling.py` | 25 unit tests for the interval, daily, weekly, monthly recurrence scheduling fix. |
| `requirements.txt` | Python package dependencies for the project. |
| `reminders.db` | Auto-created SQLite database on first run. Holds users, reminders, and fired_instances tables. |
| `.env` | Contains `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY`. **Never committed.** |

---

## 📦 Installation

### Prerequisites

- **Python 3.11+** installed on your system
- **Telegram Bot Token** from [@BotFather](https://t.me/botfather)
- **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com/)

### Setup Steps

```bash
# 1. Clone the repository
git clone https://github.com/riteshpatil9686-lgtm/Memory-Mate.git
cd Memory-Mate

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate    # Linux/macOS
# or
venv\Scripts\activate       # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
echo 'TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here' > .env
echo 'GEMINI_API_KEY=your_gemini_api_key_here' >> .env

# 5. Run the bot
python bot.py
```

---

## 🔐 Environment Variables

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
```

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Token from [@BotFather](https://t.me/botfather). Used to authenticate with the Telegram Bot API. |
| `GEMINI_API_KEY` | ✅ | API key from [Google AI Studio](https://aistudio.google.com/). Powers the natural language parser. |

> ⚠️ **Security**: Never commit `.env` to version control. The `.gitignore` already excludes it.

---

## 📖 Usage Guide

### Command Reference

| Command | Description | Example |
|---|---|---|
| `/start` | Initialize the bot and see help | `/start` |
| `/help` | Show help message | `/help` |
| `/add <message>` | Create a reminder using natural language | `/add Buy milk tomorrow at 5pm` |
| `/reminders` | List all pending reminders | `/reminders` |
| `/today` | Show reminders due today | `/today` |
| `/week` | Show reminders due this week | `/week` |
| `/complete <id>` | Mark a reminder as done | `/complete 5` |
| `/cancel <id>` | Delete a reminder | `/cancel 5` |
| `/stop <id>` | Stop a recurring series (keeps future reminders, removes recurrence) | `/stop 5` |
| `/brief` | Toggle morning brief on/off | `/brief` |

### Natural Language Examples

| You Say | What Happens |
|---|---|
| `/add Buy groceries tomorrow at 5pm` | Single reminder for tomorrow 5:00 PM IST |
| `/add Drink water every 30 minutes` | Recurring interval reminder every 30 minutes |
| `/add Standup reminder every day at 9 AM` | Daily recurring reminder at 9:00 AM IST |
| `/add Gym every Monday and Wednesday at 6pm` | Weekly recurring reminder Mon/Wed at 6:00 PM IST |
| `/add Pay rent every month on the 1st at 9am` | Monthly recurring reminder on the 1st at 9:00 AM IST |
| `/add Renew license every year on June 15` | Yearly recurring reminder |
| `/add Meeting tomorrow at 3pm` | Also works without explicit "remind me" |
| `/add Remind me 30 min before the meeting tomorrow at 3pm` | Dual-time: event at 3pm, reminder at 2:30pm |

### Interactive Buttons

When a reminder fires, you'll see:

```
🧠 Reminder!
Drink water
🕐 02:30 PM IST

[ ✅ Done ] [ 😴 Snooze 5m ]
```

- **Done** → Marks the reminder as completed
- **Snooze 5m** → Reschedules it 5 minutes later

---

## 🗄️ Database Schema

```sql
-- Users table: stores Telegram user profiles and preferences
CREATE TABLE users (
    user_id             INTEGER PRIMARY KEY,       -- Telegram user ID
    chat_id             INTEGER UNIQUE NOT NULL,   -- Telegram chat ID
    name                TEXT NOT NULL,              -- User's display name
    timezone            TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    morning_brief_enabled INTEGER DEFAULT 1,       -- 0 = disabled, 1 = enabled
    morning_brief_time  TEXT DEFAULT '08:00',       -- HH:MM format in IST
    last_brief_date     TEXT,                       -- ISO date of last brief sent
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reminders table: stores all reminder schedules
CREATE TABLE reminders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,           -- FK to users.user_id
    chat_id             INTEGER NOT NULL,           -- Destination chat
    message             TEXT NOT NULL,              -- Reminder message text
    remind_at           TEXT NOT NULL,              -- ISO 8601 UTC timestamp
    recurrence          TEXT,                       -- 'interval', 'daily', 'weekly', 'monthly', etc.
    recurrence_rule     TEXT,                       -- JSON: {"type":"interval","minutes":30}
    event_datetime      TEXT,                       -- ISO 8601 for event-based reminders
    reminder_offset     TEXT,                       -- e.g. '30min', '1h'
    task_title          TEXT,                       -- Cleaned task title
    is_sent             INTEGER DEFAULT 0           -- 0 = pending, 1 = fired/completed
);

-- Fired instances: deduplication log for recurring reminders
CREATE TABLE fired_instances (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id         INTEGER NOT NULL,           -- FK to reminders.id
    scheduled_at        TEXT NOT NULL,              -- ISO 8601 UTC
    UNIQUE(reminder_id, scheduled_at)
);
```

### Entity-Relationship Diagram

```
users (1) ─────< (N) reminders (1) ─────< (N) fired_instances
  │                     │
  │                     └── Stores recurrence rules as JSON
  └── Stores user preferences (brief toggle, timezone)
```

---

## 🔄 System Workflow

### 1. Reminder Creation Flow

```
User sends /add <message>
        │
        ▼
┌────────────────┐
│ parse_reminder_ │───▶ Gemini 2.0 Flash (primary parser)
│ extended()      │    └── Success → structured JSON
│                 │    └── Failure → fallback to dateparser
└────────┬───────┘
         │
         ▼
┌────────────────┐
│ parse_recurrence│───▶ Regex-based: 'every N hours', 'daily', 'weekly', etc.
│ (text)         │    └── Fallback: text-level regex when parser misses minutes
└────────┬───────┘
         │
         ▼
┌────────────────┐
│ Interval Fix   │───▶ If type == 'interval':
│ add_reminder() │    first_run = now + interval_delta
│                │    Overrides raw parsed time
└────────┬───────┘
         │
         ▼
┌────────────────┐
│ SQLite INSERT  │───▶ remind_at = corrected first_run (or parsed time for non-interval)
│                │    recurrence_rule = JSON string
└────────┬───────┘
         │
         ▼
┌────────────────┐
│ APScheduler    │───▶ job_queue.run_once(when=ra_utc)
│ JobQueue       │    Name = 'r<reminder_id>'
└────────────────┘
```

### 2. Reminder Firing Flow (Recurring)

```
APScheduler fires job
        │
        ▼
┌────────────────────┐
│ send_reminder_     │───▶ Fetch reminder from DB
│ callback()         │───▶ Send Telegram message with Done/Snooze buttons
│                    │───▶ Mark this instance in fired_instances
└────────┬──────────┘
         │
         ▼
┌────────────────────┐
│ Compute next       │───▶ interval: base + delta (hours/minutes/days)
│ occurrence         │───▶ daily: base + 1 day
│                    │───▶ weekly: advance to next matching weekday
│                    │───▶ monthly: advance to next month's day
│                    │───▶ yearly: base + 1 year
└────────┬──────────┘
         │
         if next_dt > now:
         │
         ▼
┌────────────────────┐
│ Schedule next      │───▶ UPDATE remind_at in DB
│ recurrence         │───▶ run_once(when=next_dt)
│                    │
│ else (end of series)│
│  ──▶ Mark is_sent=1 │
└────────────────────┘
```

### 3. Startup Recovery Flow

```
Bot starts
    │
    ▼
┌────────────────┐
│ recover_missed │───▶ Find all is_sent=0 WHERE remind_at <= now
│ ()             │───▶ For each missed reminder:
│                │       - Send "(missed)" notification
│                │       - If recurring:
│                │           While next_dt <= now:
│                │               Advance by recurrence rule
│                │           Schedule next valid occurrence
│                │       - If not recurring: mark is_sent=1
└────────────────┘
```

---

## ⏰ Scheduling System

The scheduling system is the core of Memory Mate. It uses **APScheduler** (embedded in python-telegram-bot's `JobQueue`) for job management.

### Interval Scheduling Fix

Memory Mate implements a critical fix for interval-based reminders:

```
Problem:  dateparser returns ≈now for "every 30 minutes" texts.
          APScheduler fires at the raw parsed time → immediate fire.

Fix:      In add_reminder(), if recurrence type is 'interval':
          first_run = datetime.now(UTC) + interval_delta
          ra_utc     = first_run  ← overrides parsed time
```

### Recurrence Rule Format

Recurrence rules are stored as JSON in the `recurrence_rule` column:

```json
{"type": "interval", "minutes": 30}
{"type": "interval", "hours": 2}
{"type": "interval", "days": 1}
{"type": "daily"}
{"type": "weekly", "days": [0]}           /* Monday */
{"type": "weekly", "days": [0, 1, 2, 3, 4]}  /* Weekdays */
{"type": "monthly", "day": 1}
{"type": "yearly"}
```

### Duplicate Prevention

- Each job has a unique name `r<reminder_id>`
- The `fired_instances` table logs each fired occurrence with a `UNIQUE(reminder_id, scheduled_at)` constraint
- `recover_missed()` and `periodic_check()` check `get_jobs_by_name()` before registering new jobs

---

## 🧪 Testing

```bash
# Run all scheduling tests
python -m pytest test_recurrence_scheduling.py -v

# Run with coverage
python -m pytest test_recurrence_scheduling.py -v --cov=bot
```

### Test Coverage

| Test Class | Tests | What It Verifies |
|---|---|---|
| `TestIntervalFirstFire` | 6 | `every 30m`, `every 2h`, `every 6h` first fire = `now + interval` |
| `TestDailyFirstFire` | 3 | Next 8 AM computed correctly (before/after current time) |
| `TestWeeklyFirstFire` | 4 | Next Monday from Wednesday, from Monday morning |
| `TestMonthlyFirstFire` | 3 | Next 1st of month before/after the target day |
| `TestDuplicateJobPrevention` | 2 | `get_jobs_by_name()` used as dedup check |
| `TestTimezoneAwareness` | 2 | UTC-aware timestamps preserved through fix |
| `TestSendReminderCallbackRecurrence` | 5 | Next occurrence computed correctly for all types |

---

## 🚀 Deployment

### Production Deployment

```bash
# Using nohup
nohup python bot.py > bot.log 2>&1 &

# Using systemd (Linux)
[Unit]
Description=Memory Mate Telegram Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/Memory-Mate
ExecStart=/path/to/venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Quick PID Launcher (Dev)

```bash
python launcher.py
# Starts bot in background, writes PID to bot.pid
# View logs: tail -f bot.log
```

---

## ⚙️ Configuration

All configuration is via environment variables in `.env`. No configuration files are needed.

| Setting | Source | Default |
|---|---|---|
| Bot token | `.env` | — |
| Gemini API key | `.env` | — |
| Timezone | Hardcoded | `Asia/Kolkata` |
| Morning brief time | `users.morning_brief_time` | `08:00` |
| Morning brief enabled | `users.morning_brief_enabled` | `1` (enabled) |
| Periodic check interval | Hardcoded | 30 seconds |
| Snooze duration | Hardcoded | 5 minutes |

---

## ⚡ Performance Optimizations

1. **WAL mode** — SQLite is configured with `PRAGMA journal_mode=WAL` for concurrent read/write performance
2. **Minimal stack** — Single-file bot, no external task queue, no Docker overhead
3. **Cached DB connections** — `get_db()` creates fresh connections per call (safe for async)
4. **Lightweight scheduler** — APScheduler JobQueue is purpose-built for telegram-bot workloads
5. **Fired-instance dedup** — Unique constraint prevents duplicate processing on recovery
6. **Unbuffered logging** — `python -u` mode for real-time log output in production

---

## 🔒 Security Considerations

1. **Token security** — Bot token and API key stored exclusively in `.env` (never in code)
2. **`.gitignore`** — `.env`, `*.db`, `__pycache__/` all excluded from version control
3. **Input validation** — User input is sanitized via `clean_title()` and length-limited to 200 chars
4. **SQL injection** — All queries use parameterized statements (`?` placeholders) exclusively
5. **User isolation** — Reminders are scoped by `user_id`; `/complete`, `/cancel`, `/stop` all verify ownership
6. **Rate limiting** — Telegram's built-in rate limiting applies (no custom ratelimit needed)
7. **Minimal attack surface** — No webhooks, no HTTP server, no Docker exposed ports
8. **Error containment** — All API calls wrapped in try/except; failures logged without crashing

---

## 🛡️ Error Handling Strategy

| Error Type | Handling |
|---|---|
| Gemini API failure | Log warning, fall back to `dateparser` |
| Date parsing failure | Reply "Could not understand when" |
| DB constraints | `INSERT OR IGNORE` for dedup, `get_db()` per call |
| Job scheduling failure | Log error, don't crash |
| Send message failure | Log error, continue processing |
| Periodic check failure | Catch all exceptions, silently continue |
| Malformed recurrence | Parse error → skip recurrence, treat as one-shot |

---

## 📊 Logging & Monitoring

### Log Format
```
2026-06-28 12:33:15,958 [INFO] Database initialized
2026-06-28 12:33:16,898 [INFO] Starting up...
2026-06-28 12:33:16,902 [INFO] Morning brief scheduled for user 7242297427 at 08:00
```

### Log Levels Used
- **INFO** — Normal operations: startup, scheduling, sends
- **WARNING** — Recoverable issues: Gemini parse failure, send failures
- **ERROR** — Critical: APScheduler conflicts, crash causes

### Key Log Events
- `Database initialized` — Startup complete
- `Recovering N missed` — Found and rescheduling missed reminders
- `Sent #N` — Reminder delivered successfully
- `Recurrence #N next at ...` — Next occurrence scheduled
- `Morning brief sent to user N` — Daily brief dispatched

---

## 📐 Coding Standards

- **Style**: PEP 8 with type hints where practical
- **Async**: All handlers use `async def` with `await`
- **DB**: Parameterized queries (`?` placeholders, never f-strings)
- **Logging**: Structured log messages with context. One log line per significant event.
- **Error handling**: Always use specific exception types; catch broadly only at handler boundaries
- **Naming**: snake_case for functions/variables, UPPER_CASE for constants
- **Formatting**: Black-compatible (120 char lines)

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Before Submitting
```bash
# Run tests
python -m pytest test_recurrence_scheduling.py -v
# Check syntax
python -m py_compile bot.py
```

---

## 🗺️ Roadmap

- [ ] **Multi-timezone support** — User-configurable timezones per profile
- [ ] **Custom morning brief time** — Per-user configurable via command
- [ ] **Recurrence list view** — See all active recurring series
- [ ] **Photo/video reminders** — Attach media to reminders
- [ ] **Group chat support** — Shared reminders in group chats
- [ ] **Web dashboard** — Optional web UI for managing reminders (future)
- [ ] **iCal export** — Export reminders to calendar format
- [ ] **Push notification resilience** — Exponential backoff for failed sends

---

## 🔧 Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| Bot doesn't respond | Token missing or invalid | Check `.env` has correct `TELEGRAM_BOT_TOKEN` |
| "Gemini parse failed" | API key invalid or quota exceeded | Check `.env` has valid `GEMINI_API_KEY` |
| "Conflict" errors | Another bot instance running | Kill other instances: `pkill -f "python bot.py"` |
| Reminder fires immediately | Old scheduling bug (pre-fix) | Update to latest code; `remind_at` now uses `now + interval` |
| "Could not understand when" | Dateparser couldn't parse | Try more explicit phrasing: "tomorrow at 5pm" → "2026-06-29 17:00" |
| Recurring reminder stopped | /stop command used | Create a new reminder with `/add` |
| Morning brief not arriving | Feature disabled by `/brief` toggle | Run `/brief` to re-enable |

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.

---

## 🙏 Credits

- **[python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)** — Robust Telegram bot framework
- **[Google Gemini API](https://ai.google.dev/)** — Natural language understanding
- **[dateparser](https://github.com/scrapinghub/dateparser)** — Date parsing fallback
- **[APScheduler](https://github.com/agronholm/apscheduler)** — Reliable job scheduling (via PTB)
- **[@BotFather](https://t.me/botfather)** — Telegram bot creation and management

---

<p align="center">
  <sub>Built with ❤️ by Ritesh Patil</sub>
  <br>
  <sub>Powered by Nous Research Hermes Agent</sub>
</p>
