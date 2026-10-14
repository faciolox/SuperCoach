from telegram import Update
from telegram.ext import ContextTypes
import app.database as db
from app.gemini_coach import genera_piano_allenamento
import app.strava_client as strava
from app.gemini_coach import analizza_uscita
from app.gemini_coach import analizza_uscite_settimanali
from datetime import datetime, date

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
    try:
        chat_id = update.effective_chat.id
        utente = db.get_user(chat_id)
        print(f"{datetime.isoformat()}: Richiesta piano")
        if utente.get("stato") == "ACTIVE" and "piano_corrente" in utente.get("profilo", {}):
            messaggio_completo = utente["profilo"]["piano_corrente"]
            
            MAX_LEN = 4000
            
            while len(messaggio_completo) > 0:
                if len(messaggio_completo) <= MAX_LEN:
                    await update.message.reply_text(messaggio_completo)
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
                await update.message.reply_text(messaggio_completo[:punto_taglio])
                
                # Rimuove la parte inviata dalla stringa totale e toglie eventuali spazi vuoti all'inizio
                messaggio_completo = messaggio_completo[punto_taglio:].lstrip()
        else:
            await update.message.reply_text("Non hai nessun piano attivo al momento. Usa /start per crearne uno nuovo.")
    except Exception as e:
        print(f"{datetime.isoformat()}: Errore {e}")
async def cancella_piano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancella il piano e disattiva il bot per l'utente."""
    try:
        print("Richiesta Cancellazione piano")
        chat_id = update.effective_chat.id
        
        db.update_user_state(chat_id, "PAUSED", step=None)
        db.update_user_profile(chat_id, "piano_corrente", None)
        
        await update.message.reply_text(
            "🗑️ Il tuo piano di allenamento è stato cancellato definitivamente. L'analisi automatica di Strava è disattivata.\n\n"
            "Usa /start se vorrai crearne uno nuovo in futuro."
        )
    except Exception as e:
        print(f"{datetime.isoformat()}: Errore {e}")
async def uscite_settimanali(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recupera e analizza le uscite della settimana da Strava su richiesta."""
    chat_id = update.effective_chat.id
    utente = db.get_user(chat_id)
    print("richiesta uscite settimanali")
    await update.message.reply_text("🔄 Sto interrogando i server di Strava per le attività di questa settimana...")
    try:
        dati_strava = strava.get_last_week_activities()
    except:
        await update.message.reply_text("❌ C'è stato un problema nell'estrazione dei dettagli dell'attività.")
        return
    
    if dati_strava:
        try:
            analisi = analizza_uscite_settimanali(dati_strava)
        except:
            await update.message.reply_text("❌ C'è stato un problema nell'estrazione dei dettagli dell'attività.")
            return
        messaggio_completo = f"Ecco l'analisi delle tue uscite:\n\n{analisi}"
        MAX_LEN = 4000

        while len(messaggio_completo) > 0:
            if len(messaggio_completo) <= MAX_LEN:
                await update.message.reply_text(messaggio_completo)
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
            await update.message.reply_text(messaggio_completo[:punto_taglio])
            
            # Rimuove la parte inviata dalla stringa totale e toglie eventuali spazi vuoti all'inizio
            messaggio_completo = messaggio_completo[punto_taglio:].lstrip()
    else:
        await update.message.reply_text("❌ C'è stato un problema nell'estrazione dei dettagli dell'attività.")

async def ultima_uscita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recupera e analizza l'ultima uscita da Strava su richiesta."""
    chat_id = update.effective_chat.id
    utente = db.get_user(chat_id)
    print("richiesta ultima uscita")

    await update.message.reply_text("🔄 Sto interrogando i server di Strava per la tua ultima attività...")
    
    # 1. Trova l'ID
    try:
        activity_id = strava.get_latest_activity_id()
    except:
        await update.message.reply_text("❌ C'è stato un problema nell'estrazione dei dettagli dell'attività.")
    if not activity_id:
        await update.message.reply_text("❌ Non ho trovato nessuna attività recente sul tuo profilo Strava o c'è un errore di connessione.")
        return
        
    # 2. Scarica i dati puliti (zone, segmenti, ecc.)
    try:
        dati_strava = strava.format_strava_data_for_gemini(activity_id)
    except:
        await update.message.reply_text("❌ C'è stato un problema nell'estrazione dei dettagli dell'attività.")
        return
    
    if dati_strava:
        # 3. Passa i dati a Gemini
        analisi = analizza_uscita(dati_strava)
        await update.message.reply_text(f"🚴‍♂️ **Report Ultima Uscita:**\n\n{analisi}")
    else:
        await update.message.reply_text("❌ C'è stato un problema nell'estrazione dei dettagli dell'attività.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Smista i messaggi di testo in base allo stato in cui si trova l'utente."""
    print("richiesta creazione piano")
    chat_id = update.effective_chat.id
    testo = update.message.text
    
    utente = db.get_user(chat_id)
    stato = utente.get("stato")
    step = utente.get("step")
    
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
            db.update_user_state(chat_id, "ONBOARDING", step=5)
            await update.message.reply_text("Quando vuoi iniziare il piano?")
        elif step == 5:
            db.update_user_profile(chat_id,"data inizio piano", testo)
            db.update_user_state(chat_id, "ACTIVE", step=None)   
            await update.message.reply_text("Perfetto! Sto elaborando il tuo profilo e generando il piano di allenamento con Gemini. Un attimo di pazienza... 🚴‍♂️")
            
            utente_aggiornato = db.get_user(chat_id)
            profilo = utente_aggiornato["profilo"]
            
            piano_generato = genera_piano_allenamento(profilo)
            
            # Salva il piano nel database
            db.update_user_profile(chat_id, "piano_corrente", piano_generato)
            messaggio_completo = f"Ecco il tuo piano strutturato:\n\n{piano_generato}"
            MAX_LEN = 4000

            while len(messaggio_completo) > 0:
                if len(messaggio_completo) <= MAX_LEN:
                    await update.message.reply_text(messaggio_completo)
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
                await update.message.reply_text(messaggio_completo[:punto_taglio])
                
                # Rimuove la parte inviata dalla stringa totale e toglie eventuali spazi vuoti all'inizio
                messaggio_completo = messaggio_completo[punto_taglio:].lstrip()
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