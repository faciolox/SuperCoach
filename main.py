import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
from app.bot_handlers import start, interrompi_piano, handle_text, mostra_piano, cancella_piano, ultima_uscita, uscite_settimanali, invia_testo_lungo
from app.models import formatta_piano
import app.database as db
import app.strava_client as strava
import app.gemini_coach as coach
import app.database as db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
import time as sl
from datetime import datetime, date, timedelta
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
bot_app.add_handler(CommandHandler("settimana",uscite_settimanali))

# 2. Gestione del ciclo di vita dell'applicazione
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    print("✅ Bot Telegram avviato in modalità polling.")
    # Debug: mostra quale bot è associato al token caricato
    print(f"🤖 Bot in uso: @{bot_app.bot.username}")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        routine_settimanale_piani, # Assicurati che questa funzione sia definita sopra!
        trigger=CronTrigger(day_of_week='mon', hour=10, minute=15, timezone='Europe/Rome')
    )
    scheduler.start()
    print("⏰ Scheduler avviato: i piani verranno inviati ogni lunedì alle 07:00")

    yield
    print("🛑 Spegnimento del bot in corso...")
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()

# Inizializza FastAPI
app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": "SuperCoach è sveglio!"}

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
    sl.sleep(60)
    print(f"🔔 Ricevuto evento da Strava: {payload}")
    
    if payload.get("aspect_type") == "create" and payload.get("object_type") == "activity":
        activity_id = payload.get("object_id")
        
        # Estrai i dati
        dati_strava = strava.format_strava_data_for_gemini(activity_id)
        
        if dati_strava:
            # Invia a tutti gli utenti attivi
            utenti = db._load_db()
            for chat_id, data in utenti.items():
            # Analizza con Gemini
                uscita = db.get_activity(chat_id, dati_strava["strava_id"])
                if not uscita and data.get("stato") == "ACTIVE":
                    analisi_testo = coach.analizza_uscita(
                        dati_strava,
                        profilo=data.get("profilo", {}),
                        allenamento_previsto=db.get_workout_by_date(chat_id, dati_strava["Start time"]),
                    )
                    db.save_activity(chat_id,activity_id,'',analisi_testo)
                    messaggio_finale = f"🚴‍♂️ **Nuova attività rilevata!**\n\n{analisi_testo}"
                    
                else:
                    continue
                try:
                    await bot_app.bot.send_message(chat_id=chat_id, text=messaggio_finale, parse_mode='Markdown')
                except telegram.error.BadRequest as e:
                    print(f"⚠️ Errore Markdown intercettato: invio come testo semplice. Dettaglio: {e}")
                    await bot_app.bot.send_message(chat_id=chat_id, text=messaggio_finale)
                    
    return {"status": "ok"}


async def routine_settimanale_piani() -> None:
    """Invia ogni lunedì il piano della settimana a tutti gli utenti attivi.

    Per ogni utente con stato ``ACTIVE``:

    - piano non ancora iniziato: nessun invio;
    - settimana 1: invia gli allenamenti già generati all'onboarding;
    - dalla settimana 2: chiede a Gemini l'aggiornamento della settimana in
      base alle uscite fatte, lo salva nel database e lo invia con il feedback.

    Un errore su un utente viene registrato nei log e non blocca gli altri.
    """
    print("🌅 Inizio generazione automatica dei piani settimanali...")

    for chat_id, dati_utente in db._load_db().items():
        if dati_utente.get("stato") != "ACTIVE":
            continue
        print(f"Aggiornamento piano per l'utente {chat_id}...")

        try:
            settimana = coach.calcola_settimana_piano(dati_utente["profilo"]["data inizio piano"])

            if settimana < 1:
                print(f"ℹ️ Il piano di {chat_id} non è ancora iniziato.")
                continue

            if settimana == 1:
                # La prima settimana è già stata generata durante l'onboarding
                testo = f"Sei alla prima settimana! Ecco il tuo piano:\n\n{formatta_piano(db.get_plan(chat_id))}"
            else:
                aggiornamento = coach.aggiorna_piano(dati_utente, settimana)
                if aggiornamento is None:
                    print(f"❌ Aggiornamento del piano non riuscito per {chat_id}.")
                    continue

                db.save_plan(chat_id, [a.model_dump() for a in aggiornamento.allenamenti])
                testo = (
                    f"Feedback della settimana {settimana - 1}:\n{aggiornamento.commento}\n\n"
                    f"Ecco il piano della settimana {settimana}:\n\n"
                    f"{formatta_piano(aggiornamento.allenamenti)}"
                )

            await invia_testo_lungo(bot_app.bot, chat_id, testo)
            print(f"✅ Piano inviato con successo a {chat_id}")

            # Pausa tra un utente e l'altro per non saturare le API di Telegram/Gemini
            await asyncio.sleep(2)
        except Exception as e:
            print(f"❌ Errore con l'utente {chat_id}: {e}")