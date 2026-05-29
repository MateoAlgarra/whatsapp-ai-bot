# 💬 WhatsApp AI Business Bot

> AI-powered WhatsApp bot for any business. Auto-detects language, books appointments, remembers conversations and works 24/7 — fully customizable in minutes.

**by [Mateo Algarra](https://github.com/MateoAlgarra)**

---

## ✨ Features

- 🌍 **25+ languages** — auto-detects and replies in the customer's language
- 🧠 **Conversation memory** — remembers context across the full chat
- 📅 **Appointment booking** — collects name, service and date automatically
- 💾 **SQLite database** — stores contacts, messages and appointments
- ⚙️ **Zero-code customization** — change the `.env` file for any business
- 📊 **Stats dashboard** — live endpoint showing contacts, messages and languages
- 🧪 **CLI test mode** — test without Twilio using `--test`
- 🔌 **REST API** — FastAPI with `/webhook`, `/health`, `/stats`, `/appointments`

---

## 🌍 Supported Languages

Spanish · English · Portuguese · French · German · Italian · Chinese · Japanese · Korean · Arabic · Russian · Hindi · Dutch · Polish · Turkish · Swedish · Danish · Finnish · Norwegian · Czech · Romanian · Hungarian · Ukrainian · Indonesian · Vietnamese · Thai

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure your business
cp .env.example .env
# Edit .env with your keys and business info

# 3. Test without Twilio first
python whatsapp_ai_bot.py --test

# 4. Run the server
uvicorn whatsapp_ai_bot:app --reload --port 8000

# 5. Expose publicly (for Twilio webhook)
ngrok http 8000

# 6. Paste the ngrok URL into Twilio WhatsApp sandbox
# https://console.twilio.com → Messaging → Try WhatsApp
```

---

## ⚙️ Configuration (.env)

```env
# OpenAI
OPENAI_API_KEY=sk-...

# Twilio
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_WHATSAPP_NUM=whatsapp:+14155238886

# Your Business
BUSINESS_NAME=Salón Valentina
BUSINESS_TYPE=salon
BUSINESS_CITY=Bogotá
BUSINESS_PHONE=+57 300 123 4567
BUSINESS_ADDRESS=Calle 72 # 10-45
BUSINESS_HOURS=Lunes a Sábado 9am–7pm
BUSINESS_SERVICES=Corte, Coloración, Uñas
AGENT_NAME=Maya
```

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/webhook` | POST | Twilio incoming message handler |
| `/health` | GET | Server health + basic stats |
| `/stats` | GET | Full stats + language breakdown |
| `/appointments` | GET | List all appointments |

---

## 🗂️ Database Schema

```
conversations  → phone, role, content, language, created_at
appointments   → phone, name, service, date_time, status
contacts       → phone, name, language, first_seen, last_seen, msg_count
```

---

## 💼 Use Cases

- Salons, barbershops, spas — appointment booking
- Clinics and dental offices — patient scheduling
- Restaurants — reservations and menu questions
- Retail stores — product inquiries and orders
- Real estate — property inquiries
- Any SMB needing 24/7 customer support

---

## 🛠️ Tech Stack

`Python` · `FastAPI` · `Twilio` · `OpenAI GPT-4o-mini` · `SQLite` · `langdetect` · `uvicorn`

---

## 📬 Contact

Need this bot set up for your business?
**[hire me on Freelancer](https://www.freelancer.com/u/MATEOAIGARRA)**
