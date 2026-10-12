import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
from app.bot_handlers import start, interrompi_piano, handle_text, mostra_piano, cancella_piano, ultima_uscita
import app.database as db
import app.strava_client as strava
import app.gemini_coach as coach


load_dotenv()

# 1. Configurazione del Bot Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot_app = Application.builder().token(TELEGRAM_TOKEN).build()

# Registra i comandi e i messaggi
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("stop", interrompi_piano))
bot_app.add_handler(CommandHandler("piano", mostra_piano))
bot_app.add_handler(CommandHandler("cancella", cancella_piano))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
bot_app.add_handler(CommandHandler("ultima", ultima_uscita))


# 2. Gestione del ciclo di vita dell'applicazione
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    print("✅ Bot Telegram avviato in modalità polling.")
    yield
    print("🛑 Spegnimento del bot in corso...")
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()

# Inizializza FastAPI
app = FastAPI(lifespan=lifespan)

# 3. Endpoint per la verifica iniziale del Webhook di Strava
@app.get("/webhook/strava")
async def verify_strava(request: Request):
    """Verifica dell'iscrizione del webhook su Strava."""
    challenge = request.query_params.get("hub.challenge")
    verify_token = request.query_params.get("hub.verify_token")
    
    # La password che hai salvato su Render (es. "SuperCoach123")
    MIO_TOKEN = os.getenv("STRAVA_VERIFY_TOKEN")
    
    # Controlliamo che il token inviato da Strava sia uguale al tuo
    if challenge and verify_token == MIO_TOKEN:
        print("✅ Webhook Strava verificato con successo!")
        return {"hub.challenge": challenge}
        
    print("❌ Errore: Token non valido o challenge mancante")
    return {"error": "Verifica fallita"}

# 4. Endpoint per ricevere i dati degli allenamenti (Post-Uscita)
@app.post("/webhook/strava")
async def strava_webhook(request: Request):
    """Ricezione delle notifiche di nuove attività da Strava."""
    payload = await request.json()
    print(f"🔔 Ricevuto evento da Strava: {payload}")
    
    if payload.get("aspect_type") == "create" and payload.get("object_type") == "activity":
        activity_id = payload.get("object_id")
        
        # Estrai i dati
        dati_strava = strava.format_strava_data_for_gemini(activity_id)
        
        if dati_strava:
            # Analizza con Gemini
            analisi_testo = coach.analizza_uscita(dati_strava)
            
            # Invia a tutti gli utenti attivi
            utenti = db._load_db()
            for chat_id, data in utenti.items():
                if data.get("stato") == "ACTIVE":
                    messaggio_finale = f"🚴‍♂️ **Nuova attività rilevata!**\n\n{analisi_testo}"
                    await bot_app.bot.send_message(chat_id=chat_id, text=messaggio_finale, parse_mode='Markdown')
                    
    return {"status": "ok"}