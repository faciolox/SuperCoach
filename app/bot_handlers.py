from telegram import Update
from telegram.ext import ContextTypes
import app.database as db
from app.gemini_coach import genera_piano_allenamento
import app.strava_client as strava
from app.gemini_coach import analizza_uscita


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inizializza l'utente e avvia il processo di onboarding."""
    chat_id = update.effective_chat.id
    db.update_user_state(chat_id, "ONBOARDING", step=0)
    
    benvenuto = (
        "Ciao! Sono il tuo AI Cycling Coach personale.\n\n"
        "Prima di creare il tuo piano di allenamento, ho bisogno di alcune informazioni. "
        "Rispondi a queste domande.\n\n"
        "1️⃣ Qual è il tuo obiettivo principale? (es. Preparare una Granfondo, "
        "migliorare in salita, fondo aerobico...)"
    )
    await update.message.reply_text(benvenuto)

async def interrompi_piano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mette in pausa il piano attuale."""
    chat_id = update.effective_chat.id
    db.update_user_state(chat_id, "PAUSED", step=None)
    
    await update.message.reply_text(
        "Piano di allenamento interrotto. Il webhook di Strava è disabilitato per te.\n"
        "Quando vuoi ricominciare, usa il comando /start."
    )

async def mostra_piano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra il piano attualmente salvato in memoria."""
    chat_id = update.effective_chat.id
    utente = db.get_user(chat_id)
    
    if utente.get("stato") == "ACTIVE" and "piano_corrente" in utente.get("profilo", {}):
        piano = utente["profilo"]["piano_corrente"]
        await update.message.reply_text(f"📖 **Ecco il tuo piano di allenamento attuale:**\n\n{piano}")
    else:
        await update.message.reply_text("Non hai nessun piano attivo al momento. Usa /start per crearne uno nuovo.")

async def cancella_piano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancella il piano e disattiva il bot per l'utente."""
    chat_id = update.effective_chat.id
    
    db.update_user_state(chat_id, "PAUSED", step=None)
    db.update_user_profile(chat_id, "piano_corrente", None)
    
    await update.message.reply_text(
        "🗑️ Il tuo piano di allenamento è stato cancellato definitivamente. L'analisi automatica di Strava è disattivata.\n\n"
        "Usa /start se vorrai crearne uno nuovo in futuro."
    )

async def ultima_uscita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recupera e analizza l'ultima uscita da Strava su richiesta."""
    chat_id = update.effective_chat.id
    utente = db.get_user(chat_id)
    

    await update.message.reply_text("🔄 Sto interrogando i server di Strava per la tua ultima attività...")
    
    # 1. Trova l'ID
    activity_id = strava.get_latest_activity_id()
    if not activity_id:
        await update.message.reply_text("❌ Non ho trovato nessuna attività recente sul tuo profilo Strava o c'è un errore di connessione.")
        return
        
    # 2. Scarica i dati puliti (zone, segmenti, ecc.)
    dati_strava = strava.format_strava_data_for_gemini(activity_id)
    
    if dati_strava:
        # 3. Passa i dati a Gemini
        analisi = analizza_uscita(dati_strava)
        await update.message.reply_text(f"🚴‍♂️ **Report Ultima Uscita:**\n\n{analisi}")
    else:
        await update.message.reply_text("❌ C'è stato un problema nell'estrazione dei dettagli dell'attività.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Smista i messaggi di testo in base allo stato in cui si trova l'utente."""
    chat_id = update.effective_chat.id
    testo = update.message.text
    
    utente = db.get_user(chat_id)
    stato = utente.get("stato")
    step = utente.get("step_onboarding")
    
    if stato == "ONBOARDING":
        if step == 0:
            db.update_user_profile(chat_id, "obiettivo", testo)
            db.update_user_state(chat_id, "ONBOARDING", step=1)
            await update.message.reply_text("2️⃣ In quanto tempo vuoi raggiungere questo obiettivo? (es. 3 mesi, entro fine luglio...)")
            
        elif step == 1:
            db.update_user_profile(chat_id, "timeline", testo)
            db.update_user_state(chat_id, "ONBOARDING", step=2)
            await update.message.reply_text("3️⃣ Quanti giorni a settimana puoi allenarti e con che durata? (es. Mar e Gio 1h, Domenica 3h)")
            
        elif step == 2:
            db.update_user_profile(chat_id, "giorni_disponibili", testo)
            db.update_user_state(chat_id, "ONBOARDING", step=3)
            await update.message.reply_text("4️⃣ Quali sono le tue zone di frequenza cardiaca (o FC Max)")
            
        elif step == 3:
            db.update_user_profile(chat_id, "zone_hr", testo)
            db.update_user_state(chat_id, "ONBOARDING", step=4)
            await update.message.reply_text("4️⃣ Quali e' la tua FTP? Se non la conosci scrivi sconosciuta")
        elif step == 4:
            db.update_user_profile(chat_id,"ftp", testo)
            db.update_user_state(chat_id, "ACTIVE", step=None)
            
            await update.message.reply_text("Perfetto! Sto elaborando il tuo profilo e generando il piano di allenamento con Gemini. Un attimo di pazienza... 🚴‍♂️")
            
            utente_aggiornato = db.get_user(chat_id)
            profilo = utente_aggiornato["profilo"]
            
            piano_generato = genera_piano_allenamento(profilo)
            
            # Salva il piano nel database
            db.update_user_profile(chat_id, "piano_corrente", piano_generato)
            
            await update.message.reply_text(f"Ecco il tuo piano strutturato:\n\n{piano_generato}")
            await update.message.reply_text(
                "Da questo momento, ogni volta che salverai un'attività su Strava, "
                "la analizzerò automaticamente e ti manderò il resoconto qui.\n\n"
                "Usa /piano per rileggerlo o /cancella per eliminarlo."
            )

    elif stato == "ACTIVE":
        await update.message.reply_text(
            "Il tuo piano è attivo. Sto monitorando le tue uscite su Strava in background.\n"
            "Usa /piano per leggerlo, /start per rifarlo o /cancella per eliminarlo."
        )
        
    elif stato == "PAUSED":
        await update.message.reply_text("Il tuo piano è in pausa. Scrivi /start per ricominciare.")