import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
from app.bot_handlers import start, interrompi_piano, handle_text, mostra_piano, cancella_piano, ultima_uscita, uscite_settimanali
import app.database as db
import app.strava_client as strava
import app.gemini_coach as coach
import app.database as db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
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
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        routine_settimanale_piani, # Assicurati che questa funzione sia definita sopra!
        trigger=CronTrigger(day_of_week='mon', hour=10, minute=0, timezone='Europe/Rome')
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
    print(f"🔔 Ricevuto evento da Strava: {payload}")
    
    if payload.get("aspect_type") == "create" and payload.get("object_type") == "activity":
        activity_id = payload.get("object_id")
        
        # Estrai i dati
        dati_strava = strava.format_strava_data_for_gemini(activity_id)
        
        if dati_strava:
            # Analizza con Gemini
            uscita = db.get_activity(chat_id, dati_strava["strava_id"])
            if not uscita:
                analisi_testo = coach.analizza_uscita(dati_strava)
                
                # Invia a tutti gli utenti attivi
                utenti = db._load_db()
                for chat_id, data in utenti.items():
                    if data.get("stato") == "ACTIVE":
                        messaggio_finale = f"🚴‍♂️ **Nuova attività rilevata!**\n\n{analisi_testo}"
                        try:
                            await bot_app.bot.send_message(chat_id=chat_id, text=messaggio_finale, parse_mode='Markdown')
                        except telegram.error.BadRequest as e:
                            print(f"⚠️ Errore Markdown intercettato: invio come testo semplice. Dettaglio: {e}")
                            await bot_app.bot.send_message(chat_id=chat_id, text=messaggio_finale)
                    
    return {"status": "ok"}


async def routine_settimanale_piani():
    print("🌅 Inizio generazione automatica dei piani settimanali...")
    
    # 1. Recupera tutti gli utenti dal database MongoDB
    utenti = db._load_db()
    for chat_id, dati_utente in utenti.items():
        # Opzionale: controlla se l'utente ha finito l'onboarding ed è attivo
        if dati_utente.get("stato") == "ACTIVE":
            print(f"Aggiornamento piano per l'utente {chat_id}...")
            
            try:
                messaggio = coach.aggiorna_piano(dati_utente)
                data_inizio = datetime.strptime(dati_utente["data inizio piano"],"%d/%m/%Y")
                oggi = datetime.now()
                delta = data_inizio - oggi
                week = int(delta.days/7) +1
                piano_generato = f"""
                {dati_utente.get("piano_corrente")}
                \n\n\n Questo il feedback della {week -1} e il programma aggiornato della {week}\n\n\n
                {messaggio}
                """
                
                db.update_user_profile(chat_id, "piano_corrente", piano_generato)
                # invio il messaggio su telegram
                messaggio_completo = f"Ecco l'aggiornamento del tuo piano:\n\n{messaggio}"
                MAX_LEN = 4000
        
                while len(messaggio_completo) > 0:
                    if len(messaggio_completo) <= MAX_LEN:
                        await bot_app.bot.send_message(chat_id=chat_id, text=messaggio_completo)
                        break
                        
                    # Cerca l'ultimo "a capo" entro il limite di 4000 caratteri
                    punto_taglio = messaggio_completo.rfind('\n', 0, MAX_LEN)
                    
                    # Se non trova un "a capo", cerca l'ultimo spazio bianco
                    if punto_taglio == -1:
                        punto_taglio = messaggio_completo.rfind(' ', 0, MAX_LEN)
                        
                    # Se non trova nemmeno uno spazio (improbabile), forza il taglio al limite
                    if punto_taglio == -1:
                        punto_taglio = MAX_LEN
                        
                    # Invia il blocco pulito
                    await bot_app.bot.send_message(chat_id=chat_id,text=messaggio_completo[:punto_taglio])
                    
                    # Rimuove la parte inviata dalla stringa totale e toglie eventuali spazi vuoti all'inizio
                    messaggio_completo = messaggio_completo[punto_taglio:].lstrip()
              
                print(f"✅ Piano inviato con successo a {chat_id}")
                
                # Pausa di 2 secondi tra un utente e l'altro per non floodare le API di Telegram/Gemini
                await asyncio.sleep(2)  
            except Exception as e:
                print(f"❌ Errore con l'utente {chat_id}: {e}")