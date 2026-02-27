# Sin Trade Telegram Bot (MVP)

Educational Telegram bot for structured trading learning with risk-first guidance.

## Features

- Structured learning levels (Beginner -> Intermediate -> Advanced -> Professional)
- Lesson workflow with `✅ Complete` gate before quiz starts
- AI curriculum track up to 100 lessons with 50-question quiz packs per lesson
- Optional OpenAI dynamic generation for lessons, quizzes, simulations, and daily challenges
- Button-first navigation (reply keyboard + inline action buttons)
- Practice simulation mode (`/simulate`)
- Daily challenge mode (`/dailychallenge`)
- Safety refusals for unrealistic guarantee/profit requests
- Risk reminder embedded in educational flow

## Requirements

- Python 3.10+
- Telegram bot token from BotFather

## Setup

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

Create `.env` from `.env.example` and set:

```env
TELEGRAM_BOT_TOKEN=your_real_token
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=arcee-ai/trinity-large-preview:free
OPENAI_BASE_URL=https://openrouter.ai/api/v1/chat/completions
OPENAI_APP_NAME=Sin Trade AI
OPENAI_TIMEOUT_SECONDS=20
```

## Run

```bash
python main.py
```

## Deploy 24/7

### Option A: Docker (recommended)

```bash
docker build -t sintrade-bot .
docker run -d --name sintrade-bot --restart unless-stopped --env-file .env sintrade-bot
```

Useful commands:

```bash
docker logs -f sintrade-bot
docker restart sintrade-bot
docker stop sintrade-bot
```

### Option B: Ubuntu VPS + systemd

1. Copy project to `/opt/sintrade-bot`
2. Create virtual env and install deps:

```bash
cd /opt/sintrade-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Place your `.env` at `/opt/sintrade-bot/.env`
4. Copy service file:

```bash
sudo cp deploy/sintrade-bot.service /etc/systemd/system/sintrade-bot.service
```

5. Start and enable on boot:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sintrade-bot
```

6. Check status/logs:

```bash
sudo systemctl status sintrade-bot
journalctl -u sintrade-bot -f
```

## Commands

- `/menu`
- `/profile`
- `/start`
- `/help`
- `/buttons`
- `/lesson`
- `/setlevel beginner|intermediate|advanced|professional`
- `/setaccess free|premium`
- `/setfocus spot|futures|both`
- `/simulate`
- `/dailychallenge`
- `/kill`
- `/status`
- `/reset`

## Notes

- This bot is educational and does not provide financial advice.
- No strategy guarantees profits.
- If `OPENAI_API_KEY` is missing or quota is unavailable, the bot falls back to built-in content automatically.
- For production, replace in-memory sessions with persistent storage (Redis/Postgres).

