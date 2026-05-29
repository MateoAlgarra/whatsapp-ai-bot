"""
╔══════════════════════════════════════════════════════════════════╗
║          WHATSAPP AI BUSINESS BOT  v1.0                         ║
║          by Mateo Algarra | github.com/MateoAlgarra              ║
║                                                                  ║
║  Multilingual AI-powered WhatsApp bot for any business.         ║
║  Auto-detects language · Books appointments · Answers FAQs      ║
║  Remembers conversation history · Works 24/7                    ║
║                                                                  ║
║  Stack: FastAPI · Twilio · OpenAI · SQLite · langdetect         ║
╚══════════════════════════════════════════════════════════════════╝

SETUP:
  1. pip install -r requirements.txt
  2. Copy .env.example to .env and fill in your keys
  3. uvicorn whatsapp_ai_bot:app --reload --port 8000
  4. Expose with ngrok: ngrok http 8000
  5. Paste the ngrok URL into Twilio WhatsApp sandbox webhook

REQUIREMENTS FILE (save as requirements.txt):
  fastapi
  uvicorn
  twilio
  openai
  langdetect
  python-dotenv
  colorama
  pydantic
"""

# ── Standard library ──────────────────────────────────────────────
import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from pathlib import Path

# ── Third-party ───────────────────────────────────────────────────
try:
    import uvicorn
    from fastapi import FastAPI, Request, Form
    from fastapi.responses import PlainTextResponse
    from twilio.rest import Client as TwilioClient
    from twilio.twiml.messaging_response import MessagingResponse
    from openai import OpenAI
    from langdetect import detect as detect_language, LangDetectException
    from dotenv import load_dotenv
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    print("Installing required libraries, please wait...")
    os.system(
        "pip install fastapi uvicorn twilio openai langdetect "
        "python-dotenv colorama pydantic --break-system-packages -q"
    )
    import uvicorn
    from fastapi import FastAPI, Request, Form
    from fastapi.responses import PlainTextResponse
    from twilio.rest import Client as TwilioClient
    from twilio.twiml.messaging_response import MessagingResponse
    from openai import OpenAI
    from langdetect import detect as detect_language, LangDetectException
    from dotenv import load_dotenv
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)

load_dotenv()

# ═══════════════════════════════════════════════════════════════════
#  BUSINESS CONFIGURATION — Edit this for each client
# ═══════════════════════════════════════════════════════════════════
BUSINESS = {
    "name":        os.getenv("BUSINESS_NAME",     "Mi Negocio"),
    "type":        os.getenv("BUSINESS_TYPE",     "general"),   # salon|clinic|restaurant|store|general
    "city":        os.getenv("BUSINESS_CITY",     "Bogotá"),
    "phone":       os.getenv("BUSINESS_PHONE",    "+57 300 000 0000"),
    "address":     os.getenv("BUSINESS_ADDRESS",  "Calle 123 # 45-67"),
    "hours":       os.getenv("BUSINESS_HOURS",    "Lunes a Sábado 8am–6pm"),
    "services":    os.getenv("BUSINESS_SERVICES", "Consulta, Asesoría, Soporte"),
    "website":     os.getenv("BUSINESS_WEBSITE",  ""),
    "currency":    os.getenv("BUSINESS_CURRENCY", "COP"),
    "agent_name":  os.getenv("AGENT_NAME",        "Maya"),      # Bot's name
}

# ═══════════════════════════════════════════════════════════════════
#  CREDENTIALS — Set in .env file
# ═══════════════════════════════════════════════════════════════════
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY",      "")
TWILIO_ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID",  "")
TWILIO_AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN",   "")
TWILIO_WHATSAPP_NUM = os.getenv("TWILIO_WHATSAPP_NUM", "whatsapp:+14155238886")
DB_PATH             = os.getenv("DB_PATH",              "bot_database.db")
MAX_HISTORY         = int(os.getenv("MAX_HISTORY",      "12"))   # messages to remember
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("WhatsAppBot")


# ──────────────────────────────────────────────────────────────────
#  DATABASE
# ──────────────────────────────────────────────────────────────────

def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT NOT NULL,
            role        TEXT NOT NULL,           -- 'user' | 'assistant'
            content     TEXT NOT NULL,
            language    TEXT DEFAULT 'en',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT NOT NULL,
            name        TEXT,
            service     TEXT,
            date_time   TEXT,
            status      TEXT DEFAULT 'pending',  -- pending|confirmed|cancelled
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS contacts (
            phone       TEXT PRIMARY KEY,
            name        TEXT,
            language    TEXT DEFAULT 'en',
            first_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            msg_count   INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    return conn


DB: sqlite3.Connection = None   # initialized on startup


def save_message(phone: str, role: str, content: str, language: str = "en"):
    DB.execute(
        "INSERT INTO conversations (phone, role, content, language) VALUES (?,?,?,?)",
        (phone, role, content, language)
    )
    DB.commit()


def get_history(phone: str) -> list[dict]:
    rows = DB.execute(
        "SELECT role, content FROM conversations WHERE phone=? ORDER BY created_at DESC LIMIT ?",
        (phone, MAX_HISTORY)
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def upsert_contact(phone: str, language: str = "en", name: str = None):
    existing = DB.execute("SELECT * FROM contacts WHERE phone=?", (phone,)).fetchone()
    if existing:
        DB.execute(
            "UPDATE contacts SET last_seen=CURRENT_TIMESTAMP, msg_count=msg_count+1, "
            "language=? WHERE phone=?",
            (language, phone)
        )
    else:
        DB.execute(
            "INSERT INTO contacts (phone, language, name) VALUES (?,?,?)",
            (phone, language, name)
        )
    DB.commit()


def save_appointment(phone: str, name: str, service: str, date_time: str) -> int:
    cur = DB.execute(
        "INSERT INTO appointments (phone, name, service, date_time) VALUES (?,?,?,?)",
        (phone, name, service, date_time)
    )
    DB.commit()
    return cur.lastrowid


def get_appointments(phone: str) -> list[dict]:
    rows = DB.execute(
        "SELECT * FROM appointments WHERE phone=? AND status='pending' ORDER BY created_at DESC",
        (phone,)
    ).fetchall()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────────────────────────
#  LANGUAGE DETECTION
# ──────────────────────────────────────────────────────────────────

LANGUAGE_NAMES = {
    "es": "Spanish", "en": "English", "pt": "Portuguese",
    "fr": "French",  "de": "German",  "it": "Italian",
    "zh": "Chinese", "ja": "Japanese","ko": "Korean",
    "ar": "Arabic",  "ru": "Russian", "hi": "Hindi",
    "nl": "Dutch",   "pl": "Polish",  "tr": "Turkish",
    "sv": "Swedish", "da": "Danish",  "fi": "Finnish",
    "no": "Norwegian","cs":"Czech",   "ro": "Romanian",
    "hu": "Hungarian","uk":"Ukrainian","id":"Indonesian",
    "vi": "Vietnamese","th":"Thai",
}


def detect_lang(text: str) -> str:
    try:
        if len(text.strip()) < 4:
            return "en"
        return detect_language(text)
    except LangDetectException:
        return "en"


# ──────────────────────────────────────────────────────────────────
#  SYSTEM PROMPT BUILDER
# ──────────────────────────────────────────────────────────────────

def build_system_prompt(language_code: str) -> str:
    lang_name = LANGUAGE_NAMES.get(language_code, "English")
    now = datetime.now().strftime("%A %d %B %Y, %H:%M")

    return f"""You are {BUSINESS['agent_name']}, a professional and friendly virtual assistant for {BUSINESS['name']}.

BUSINESS INFORMATION:
- Name: {BUSINESS['name']}
- Type: {BUSINESS['type']}
- Location: {BUSINESS['address']}, {BUSINESS['city']}
- Phone: {BUSINESS['phone']}
- Hours: {BUSINESS['hours']}
- Services: {BUSINESS['services']}
- Website: {BUSINESS['website'] or 'Not available'}
- Currency: {BUSINESS['currency']}
- Current date/time: {now}

YOUR ROLE:
- Answer questions about the business professionally
- Help customers book appointments when requested
- Handle complaints with empathy and offer solutions
- Provide pricing information if available
- Escalate to human when the customer is upset or has a complex issue

LANGUAGE RULE — THIS IS CRITICAL:
The customer is writing in {lang_name}. You MUST respond ONLY in {lang_name}.
Never switch languages unless the customer does first.
If you do not know {lang_name} well, approximate it gracefully.

APPOINTMENT BOOKING FLOW:
When a customer wants to book, collect in order:
1. Full name
2. Desired service
3. Preferred date and time
Then confirm all details and say "✅ Appointment confirmed!" followed by a summary.

TONE:
- Warm, professional, concise
- Use emojis sparingly (1–2 max per message)
- Keep messages under 200 words
- Never mention you are an AI unless directly asked
- If asked, say you are a virtual assistant for {BUSINESS['name']}

ESCALATION:
If the customer is very upset or asks for a human, say:
"I'll connect you with our team right away. Please call us at {BUSINESS['phone']} 
or we'll reach out to you shortly."
"""


# ──────────────────────────────────────────────────────────────────
#  OPENAI RESPONSE
# ──────────────────────────────────────────────────────────────────

def get_ai_response(phone: str, user_message: str, language: str) -> str:
    if not OPENAI_API_KEY:
        # Demo mode — returns canned response if no API key
        return demo_response(user_message, language)

    client = OpenAI(api_key=OPENAI_API_KEY)
    history = get_history(phone)

    messages = [
        {"role": "system", "content": build_system_prompt(language)},
        *history,
        {"role": "user", "content": user_message},
    ]

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"OpenAI error: {e}")
        return fallback_message(language)


def demo_response(message: str, language: str) -> str:
    """Returns a canned response when no OpenAI key is set (for testing)."""
    demos = {
        "es": f"¡Hola! Soy {BUSINESS['agent_name']} de {BUSINESS['name']}. ¿En qué puedo ayudarte hoy?",
        "en": f"Hi! I'm {BUSINESS['agent_name']} from {BUSINESS['name']}. How can I help you today?",
        "pt": f"Olá! Sou {BUSINESS['agent_name']} de {BUSINESS['name']}. Como posso ajudá-lo hoje?",
        "fr": f"Bonjour! Je suis {BUSINESS['agent_name']} de {BUSINESS['name']}. Comment puis-je vous aider?",
    }
    return demos.get(language, demos["en"])


def fallback_message(language: str) -> str:
    fallbacks = {
        "es": "Lo siento, tuve un problema técnico. Por favor intenta de nuevo en un momento.",
        "en": "Sorry, I had a technical issue. Please try again in a moment.",
        "pt": "Desculpe, tive um problema técnico. Por favor, tente novamente.",
        "fr": "Désolé, j'ai eu un problème technique. Veuillez réessayer.",
        "de": "Entschuldigung, technisches Problem. Bitte versuchen Sie es erneut.",
    }
    return fallbacks.get(language, fallbacks["en"])


# ──────────────────────────────────────────────────────────────────
#  SPECIAL COMMAND HANDLERS
# ──────────────────────────────────────────────────────────────────

COMMAND_TRIGGERS = {
    "appointments": ["my appointments", "mis citas", "minhas consultas",
                     "mes rendez-vous", "meine termine"],
    "reset":        ["reset", "restart", "reiniciar", "nueva conversación",
                     "new conversation", "começar de novo"],
    "human":        ["human", "agent", "person", "humano", "agente",
                     "pessoa", "personne", "hablar con alguien"],
}


def detect_command(message: str) -> str | None:
    msg_lower = message.lower().strip()
    for command, triggers in COMMAND_TRIGGERS.items():
        if any(t in msg_lower for t in triggers):
            return command
    return None


def handle_command(command: str, phone: str, language: str) -> str:
    if command == "appointments":
        appts = get_appointments(phone)
        if not appts:
            msgs = {
                "es": "No tienes citas programadas. ¿Deseas agendar una?",
                "en": "You have no upcoming appointments. Would you like to book one?",
                "pt": "Você não tem consultas agendadas. Deseja marcar uma?",
            }
            return msgs.get(language, msgs["en"])
        lines = [f"📅 *{a['service']}* — {a['date_time']}" for a in appts]
        header = {"es":"Tus citas:", "en":"Your appointments:", "pt":"Suas consultas:"}.get(language,"Your appointments:")
        return header + "\n" + "\n".join(lines)

    if command == "reset":
        DB.execute("DELETE FROM conversations WHERE phone=?", (phone,))
        DB.commit()
        msgs = {
            "es": f"¡Conversación reiniciada! Soy {BUSINESS['agent_name']}, ¿en qué puedo ayudarte?",
            "en": f"Conversation reset! I'm {BUSINESS['agent_name']}, how can I help?",
            "pt": f"Conversa reiniciada! Sou {BUSINESS['agent_name']}, como posso ajudar?",
        }
        return msgs.get(language, msgs["en"])

    if command == "human":
        msgs = {
            "es": f"Entendido, te conectaré con nuestro equipo. Llámanos al {BUSINESS['phone']} o te contactaremos pronto. 📞",
            "en": f"Got it! Our team will contact you shortly. You can also call {BUSINESS['phone']}. 📞",
            "pt": f"Entendido! Nossa equipe entrará em contato em breve. Ligue para {BUSINESS['phone']}. 📞",
        }
        return msgs.get(language, msgs["en"])

    return ""


# ──────────────────────────────────────────────────────────────────
#  APPOINTMENT DETECTOR
# ──────────────────────────────────────────────────────────────────

BOOK_KEYWORDS = [
    "agendar", "reservar", "cita", "turno", "appointment",
    "book", "reserve", "schedule", "consulta", "marcar",
    "agendar", "reservar", "réserver", "rendez-vous",
    "termin", "buchen", "prenota", "appuntamento",
]


def wants_to_book(message: str) -> bool:
    return any(kw in message.lower() for kw in BOOK_KEYWORDS)


# ──────────────────────────────────────────────────────────────────
#  MAIN MESSAGE PROCESSOR
# ──────────────────────────────────────────────────────────────────

def process_message(phone: str, message: str) -> str:
    """
    Full pipeline:
    1. Detect language
    2. Update contact record
    3. Check for special commands
    4. Get AI response
    5. Save to history
    6. Return reply
    """
    language = detect_lang(message)
    upsert_contact(phone, language)

    log.info(
        Fore.CYAN + f"  [{phone[-4:]}] "
        + Fore.YELLOW + f"[{language.upper()}] "
        + Style.RESET_ALL + f"{message[:60]}..."
    )

    # Special commands bypass AI
    command = detect_command(message)
    if command:
        reply = handle_command(command, phone, language)
        save_message(phone, "user",      message, language)
        save_message(phone, "assistant", reply,   language)
        return reply

    # AI response
    save_message(phone, "user", message, language)
    reply = get_ai_response(phone, message, language)
    save_message(phone, "assistant", reply, language)

    log.info(
        Fore.GREEN + f"  [{phone[-4:]}] "
        + Style.RESET_ALL + f"→ {reply[:60]}..."
    )
    return reply


# ──────────────────────────────────────────────────────────────────
#  FASTAPI APP
# ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and print startup banner."""
    global DB
    DB = init_db()
    print(Fore.CYAN + f"""
  ╔══════════════════════════════════════════════╗
  ║      WHATSAPP AI BOT  —  {BUSINESS['name']:<19}║
  ║      Agent: {BUSINESS['agent_name']:<33}║
  ║      City:  {BUSINESS['city']:<33}║
  ║      DB:    {DB_PATH:<33}║
  ║      Mode:  {'LIVE (OpenAI)' if OPENAI_API_KEY else 'DEMO (no API key)  ':<33}║
  ╚══════════════════════════════════════════════╝
""")
    yield
    DB.close()


app = FastAPI(title="WhatsApp AI Bot", lifespan=lifespan)


@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(
    From: str = Form(...),
    Body: str = Form(...),
):
    """
    Twilio sends a POST to this endpoint for every incoming WhatsApp message.
    We process and reply using TwiML.
    """
    phone   = From.replace("whatsapp:", "").strip()
    message = Body.strip()

    if not message:
        return PlainTextResponse("", status_code=200)

    reply = process_message(phone, message)

    twiml = MessagingResponse()
    twiml.message(reply)
    return PlainTextResponse(str(twiml), media_type="application/xml")


@app.get("/health")
async def health():
    contacts = DB.execute("SELECT COUNT(*) as n FROM contacts").fetchone()["n"]
    messages = DB.execute("SELECT COUNT(*) as n FROM conversations").fetchone()["n"]
    return {
        "status": "ok",
        "business": BUSINESS["name"],
        "contacts": contacts,
        "messages": messages,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/stats")
async def stats():
    """Quick stats dashboard — open in browser."""
    contacts   = DB.execute("SELECT COUNT(*) as n FROM contacts").fetchone()["n"]
    messages   = DB.execute("SELECT COUNT(*) as n FROM conversations").fetchone()["n"]
    appts      = DB.execute("SELECT COUNT(*) as n FROM appointments WHERE status='pending'").fetchone()["n"]
    languages  = DB.execute(
        "SELECT language, COUNT(*) as n FROM contacts GROUP BY language ORDER BY n DESC"
    ).fetchall()
    return {
        "business":    BUSINESS["name"],
        "total_contacts":    contacts,
        "total_messages":    messages,
        "pending_appointments": appts,
        "languages_breakdown": {r["language"]: r["n"] for r in languages},
        "generated_at": datetime.now().isoformat(),
    }


@app.get("/appointments")
async def appointments(phone: str = None):
    """List all or a specific contact's appointments."""
    if phone:
        rows = DB.execute(
            "SELECT * FROM appointments WHERE phone=? ORDER BY created_at DESC", (phone,)
        ).fetchall()
    else:
        rows = DB.execute(
            "SELECT * FROM appointments ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────────────────────────
#  CLI TEST MODE  (python whatsapp_ai_bot.py --test)
# ──────────────────────────────────────────────────────────────────

def run_cli_test():
    """Interactive test without Twilio — just talk to the bot in terminal."""
    global DB
    DB = init_db()
    test_phone = "+57000TEST"

    print(Fore.CYAN + f"""
  ╔══════════════════════════════════════════════╗
  ║   CLI TEST MODE — {BUSINESS['name']:<26}║
  ║   Type messages · 'exit' to quit            ║
  ╚══════════════════════════════════════════════╝
""")
    while True:
        try:
            user_input = input(Fore.GREEN + "  You: " + Style.RESET_ALL).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  Bye!")
            break

        if user_input.lower() in ("exit", "quit", "salir"):
            print(Fore.YELLOW + "  Exiting test mode.")
            break
        if not user_input:
            continue

        reply = process_message(test_phone, user_input)
        print(Fore.CYAN + f"  {BUSINESS['agent_name']}: " + Style.RESET_ALL + reply + "\n")


# ──────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        run_cli_test()
    else:
        uvicorn.run("whatsapp_ai_bot:app", host="0.0.0.0", port=8000, reload=True)
