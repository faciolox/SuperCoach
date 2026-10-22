import os
from pymongo import MongoClient

# Connessione al database
mongo_uri = os.getenv("MONGO_URI")
activity_name = os.getenv("ACTIVITY_DB")
users_name = os.getenv("USERS_DB")
if not mongo_uri:
    print("⚠️ Attenzione: Variabile MONGO_URI mancante!")

client = MongoClient(mongo_uri)
db_client = client["supercoach_db"]
users_collection = db_client[users_name]
activities = db_client[activity_name]
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
    if activity and activity.get("chat_id") != chat_id:
        return {}
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


def get_activity_set(chat_id: str, min:int=0, max:int =5) -> list:
    """Returns a set of the activity saved for that chat_id. You can also set a range, setted by default to the last 5 activities

    Args:
        chat_id (str): Chat id of the user
        min (int, optional): minimum limit of the array. Defaults to 0.
        max (int, optional): maximum limit of the array. Defaults to 5.

    Returns:
        list: set of the activity in the range selected
    """
    set_activity = activities.find({"chat_id":chat_id})
    if set_activity:
        set_activity= set_activity.distinct("activity_id")
        i=0
        activities_out = []
        for id in set_activity:
            if i < min:
                i += 1
            elif i >= max:
                return activities_out
            else:
                activity = get_activity(chat_id,id)
                activities_out.append(activity)
    
    return activities_out

    