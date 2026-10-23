import os
from pymongo import MongoClient
import re
from datetime import datetime
from app.models import FORMATO_DATA
# Connessione al database
mongo_uri = os.getenv("MONGO_URI")
activity_name = os.getenv("ACTIVITY_DB")
users_name = os.getenv("USERS_DB")
plans_name = os.getenv("PLANS_DB")
if not mongo_uri:
    print("⚠️ Attenzione: Variabile MONGO_URI mancante!")

client = MongoClient(mongo_uri)
db_client = client["supercoach_db"]
users_collection = db_client[users_name]
activities = db_client[activity_name]
plans_collection = db_client[plans_name]
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
    if activity.get("chat_id") != chat_id:
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

# --- FUNZIONI GESTIONE PIANI ---
def _data_allenamento(allenamento: dict) -> datetime:
    """Restituisce la data di un allenamento salvato, usata per ordinare il piano.
 
    Args:
        allenamento (dict): Allenamento nel formato di ``Allenamento.model_dump()``.
 
    Returns:
        datetime: Data dell'allenamento.
    """
    return datetime.strptime(allenamento["data"], FORMATO_DATA)
 
 
def save_plan(chat_id, nuovi_allenamenti: list[dict]) -> list[dict]:
    """Salva gli allenamenti di un utente, unendoli al piano già presente.
 
    Gli allenamenti esistenti *precedenti* alla prima data dei nuovi vengono
    mantenuti (storico); quelli dalla prima nuova data in poi vengono
    sostituiti, così un aggiornamento settimanale rimpiazza solo le
    settimane che ricalcola. Al termine gli ID vengono rinumerati da 1 in
    ordine cronologico.
 
    I documenti salvati nel vecchio formato testuale (senza il campo
    ``data``) vengono scartati.
 
    Args:
        chat_id (str | int): Chat ID dell'utente.
        nuovi_allenamenti (list[dict]): Allenamenti validati, nel formato
            di ``Allenamento.model_dump()``.
 
    Returns:
        list[dict]: Piano completo salvato, in ordine cronologico.
    """
    if not nuovi_allenamenti:
        return get_plan(chat_id)
 
    inizio_nuovi = min(_data_allenamento(a) for a in nuovi_allenamenti)
    storico = [
        a for a in get_plan(chat_id)
        if "data" in a and _data_allenamento(a) < inizio_nuovi
    ]
 
    piano = sorted(storico + list(nuovi_allenamenti), key=_data_allenamento)
    for numero, allenamento in enumerate(piano, start=1):
        allenamento["id"] = numero
 
    plans_collection.update_one(
        {"chat_id": str(chat_id)},
        {"$set": {"workouts": piano}},
        upsert=True,
    )
    return piano
 
 
def get_plan(chat_id) -> list[dict]:
    """Restituisce gli allenamenti pianificati per un utente.
 
    Args:
        chat_id (str | int): Chat ID dell'utente.
 
    Returns:
        list[dict]: Allenamenti salvati, oppure lista vuota se l'utente
            non ha ancora un piano.
    """
    plan = plans_collection.find_one({"chat_id": str(chat_id)})
    return plan.get("workouts", []) if plan else []
 
 
def delete_plan(chat_id) -> None:
    """Elimina il piano di allenamento di un utente.
 
    Args:
        chat_id (str | int): Chat ID dell'utente.
    """
    plans_collection.delete_one({"chat_id": str(chat_id)})