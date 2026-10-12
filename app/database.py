import json
import os

# Il file locale che farà da database temporaneo
DB_FILE = "users_db.json"

def _load_db():
    """Funzione interna per caricare il file JSON."""
    if not os.path.exists(DB_FILE):
        return {}
    
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def _save_db(data):
    """Funzione interna per salvare il dizionario nel file JSON."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_user(chat_id: int):
    """
    Recupera i dati di un utente tramite il suo ID Telegram.
    Se l'utente non esiste, lo crea con uno stato iniziale di ONBOARDING.
    """
    db = _load_db()
    str_chat_id = str(chat_id) # Le chiavi JSON sono sempre stringhe
    
    if str_chat_id not in db:
        # Struttura dati di base per un nuovo atleta
        db[str_chat_id] = {
            "stato": "ONBOARDING",
            "step_onboarding": 0, # Serve per tenere traccia delle domande iniziali
            "profilo": {
                "obiettivo": None,
                "timeline": None,
                "giorni_disponibili": None,
                "zone_hr": None,
                "ftp": None
            }
        }
        _save_db(db)
        
    return db[str_chat_id]

def update_user_profile(chat_id: int, key: str, value: str):
    """
    Aggiorna un singolo parametro del profilo (es. 'obiettivo', 'ftp').
    """
    db = _load_db()
    str_chat_id = str(chat_id)
    
    if str_chat_id in db:
        db[str_chat_id]["profilo"][key] = value
        _save_db(db)

def update_user_state(chat_id: int, nuovo_stato: str, step: int = None):
    """
    Aggiorna lo stato generale dell'utente (ONBOARDING, ACTIVE, PAUSED)
    e opzionalmente il punto esatto del questionario in cui si trova.
    """
    db = _load_db()
    str_chat_id = str(chat_id)
    
    if str_chat_id in db:
        db[str_chat_id]["stato"] = nuovo_stato
        if step is not None:
            db[str_chat_id]["step_onboarding"] = step
        _save_db(db)