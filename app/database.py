import os
from pymongo import MongoClient

# Connessione al database
mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    print("⚠️ Attenzione: Variabile MONGO_URI mancante!")

client = MongoClient(mongo_uri)
db_client = client["supercoach_db"]
users_collection = db_client["users"]
activities = db_client["activities"]
# --- FUNZIONI DI GESTIONE UTENTI ---

def get_user(chat_id):
    """Recupera un utente dal DB tramite il suo chat_id"""
    user = users_collection.find_one({"chat_id": str(chat_id)})
    return user if user else {}

def save_user(chat_id, data):
    """Aggiorna un utente esistente o lo crea se non esiste (upsert)"""
    data["chat_id"] = str(chat_id)
    users_collection.update_one(
        {"chat_id": str(chat_id)},
        {"$set": data},
        upsert=True
    )

def _load_db():
    """Restituisce tutti gli utenti (usato per l'invio automatico a tutti)"""
    utenti = {}
    for user in users_collection.find():
        utenti[int(user["chat_id"])] = user
    return utenti

def update_user_state(chat_id, stato, step=None):
    """Aggiorna lo stato e lo step dell'utente durante l'onboarding"""
    user = get_user(chat_id)
    user["stato"] = stato
    if step is not None:
        user["step"] = step
    save_user(chat_id, user)

def update_user_profile(chat_id, key, value):
    """Salva una singola informazione nel profilo dell'utente"""
    user = get_user(chat_id)
    if "profilo" not in user:
        user["profilo"] = {}
    user["profilo"][key] = value
    save_user(chat_id, user)
    
    
# --- FUNZIONI GESTIONE ATTIVITA' ---
def get_activity(chat_id, id):
    activity = activities.find_one({"activity_id": str(id)})
    return activity if activity else {}

def save_activity(chat_id, id, prompt="",messaggio=""):
    activities.update_one(
    {"chat_id": str(chat_id)},  # 1. Filtro: trova il documento con questo chat_id
    {"$set": {                  # 2. Aggiornamento: imposta questi campi
        "activity_id": str(id),
        "prompt": str(prompt),
        "messaggio": str(messaggio)
        }},
        upsert=True                 # 3. Opzioni: crea il documento se non esiste
    )




    