# 🚴‍♂️ SuperCoach Telegram Bot

SuperCoach è un assistente virtuale e preparatore atletico basato sull'Intelligenza Artificiale (Google Gemini), progettato per i ciclisti. Si integra direttamente con **Strava** per analizzare le attività in tempo reale e utilizza **Telegram** come interfaccia per comunicare con l'atleta.

Il bot è in grado di elaborare i dati di potenza (Watt) e frequenza cardiaca, fornendo feedback tecnici dettagliati e generando piani di allenamento personalizzati (sia per uscite outdoor che per sessioni indoor su smart trainer).

## 🌟 Funzionalità Principali

*   **Analisi Automatica Post-Uscita (Webhook):** Grazie all'integrazione con i webhook di Strava, il bot riceve istantaneamente una notifica al termine di ogni allenamento. Scarica i dati dell'attività e invia un'analisi tecnica su Telegram in modo completamente autonomo.
*   **Intelligenza Artificiale Avanzata:** Utilizza il modello **Gemini 3.8 Flash** per processare i dati in modo rapido ed economico.
*   **Knowledge Base Personalizzata (RAG):** Le analisi e i piani di allenamento si basano su un manuale tecnico avanzato (es. allenamento con power meter), caricato in memoria per istruire l'AI a utilizzare le metriche corrette (TSS, Normalized Power, Zone di potenza/cardio).
*   **Gestione Indoor/Outdoor:** L'AI è istruita per differenziare i piani di allenamento tra i giorni lavorativi (su rulli smart/Zwift) e i fine settimana (uscite su strada).
*   **Comandi su Richiesta:** L'utente può interagire con il bot in qualsiasi momento tramite comandi Telegram per richiedere le ultime statistiche o ricalcolare i piani.

## 🛠️ Tecnologie Utilizzate

*   **Python 3.10+**
*   **FastAPI / Uvicorn:** Per gestire il server web e ricevere le richieste POST (webhook) da Strava.
*   **python-telegram-bot:** Per la gestione dell'interfaccia chat di Telegram.
*   **google-genai:** SDK ufficiale per l'integrazione dei modelli Google Gemini.
*   **Strava API (v3):** Per l'estrazione dei dati degli allenamenti.
*   **Render (Cloud Hosting):** Per l'esecuzione dell'infrastruttura 24/7.

---

## 🚀 Guida all'Installazione (Sviluppo Locale)

### 1. Prerequisiti
Per far funzionare il progetto avrai bisogno di:
*   Un token API di **Telegram** (tramite BotFather).
*   Una chiave API di **Google Gemini** (tramite Google AI Studio).
*   Le credenziali API di **Strava** (Client ID e Client Secret dal tuo account sviluppatore Strava).

### 2. Clonazione e Setup
Clona il repository sul tuo computer:
```bash
git clone https://github.com/TuoNome/SuperCoach.git
cd SuperCoach
```

Crea e attiva un ambiente virtuale:
```bash
python -m venv .venv
# Su Windows:
.venv\Scripts\activate
# Su macOS/Linux:
source .venv/bin/activate
```

Installa le dipendenze:
```bash
pip install -r requirements.txt
```

### 3. Variabili d'Ambiente
Crea un file `.env` nella directory principale (questo file è ignorato da Git) e compila le seguenti chiavi:
```env
TELEGRAM_TOKEN=il_tuo_token_telegram
GEMINI_API_KEY=la_tua_chiave_gemini
STRAVA_CLIENT_ID=tuo_client_id
STRAVA_CLIENT_SECRET=tuo_client_secret
STRAVA_VERIFY_TOKEN=una_password_a_tua_scelta
```

### 4. Dati Privati e Manuali
Il bot si aspetta di trovare un file di testo contenente la teoria dell'allenamento. Crea un file denominato `manuale_potenza.txt` nella root del progetto. *Nota: anche questo file è protetto tramite `.gitignore`.*

### 5. Avvio Locale
```bash
uvicorn main:app --reload
```

---

## ☁️ Deploy in Produzione (Render)

Questo progetto è ottimizzato per il deploy su piattaforme PaaS come [Render](https://render.com/).

1.  Crea un nuovo **Web Service** su Render collegato a questo repository GitHub.
2.  Imposta lo **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3.  Aggiungi tutte le variabili d'ambiente presenti nel file `.env` direttamente nella scheda **Environment** di Render.
4.  Nella sezione **Secret Files** di Render, crea un nuovo file chiamato `manuale_potenza.txt` e incollaci dentro il testo del tuo manuale tecnico.
5.  Avvia il Deploy.

---

## 🔗 Configurazione Webhook Strava

Per abilitare l'invio automatico delle analisi post-allenamento, devi registrare l'URL pubblico del tuo bot presso i server di Strava.

Utilizza il seguente comando da terminale, sostituendo le variabili in maiuscolo con i tuoi dati reali:

```bash
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
  -d "client_id=IL_TUO_CLIENT_ID" \
  -d "client_secret=IL_TUO_CLIENT_SECRET" \
  -d "callback_url=https://IL_TUO_APP_NOME.onrender.com/webhook/strava" \
  -d "verify_token=LA_PASSWORD_SCELTA_NEL_FILE_ENV"
```

*Se la procedura va a buon fine, riceverai un ID di sottoscrizione.*

---

## 📂 Struttura del Progetto

```text
SuperCoach/
├── main.py                 # Entry point di FastAPI e Webhook
├── requirements.txt        # Dipendenze del progetto
├── .gitignore              # File esclusi dal controllo di versione
├── app/
│   ├── bot_handlers.py     # Logica e comandi del bot Telegram
│   ├── gemini_coach.py     # Integrazione AI e prompt di sistema
│   ├── strava_api.py       # Interazione con le API di Strava
│   └── database.py         # Gestione salvataggio utenti (JSON)
```

## 📝 Disclaimer
Questo progetto è stato creato a scopo personale. Segui sempre il parere di un medico sportivo o di un preparatore atletico certificato prima di intraprendere allenamenti ad alta intensità.