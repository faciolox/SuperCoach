import os
import requests
from dotenv import load_dotenv
from datetime import datetime,timedelta
import json
# Carica le variabili d'ambiente
load_dotenv()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("STRAVA_REFRESH_TOKEN")

def get_access_token():
    """
    Comunica con Strava in background usando il Refresh Token per ottenere
    un Access Token temporaneo fresco di zecca (valido 6 ore).
    """
    url = "https://www.strava.com/api/v3/oauth/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
        "f": "json"
    }
    
    response = requests.post(url, data=payload)
    
    if response.status_code != 200:
        raise Exception(f"Errore nel refresh del token Strava: {response.text}")
        
    token_data = response.json()
    return token_data["access_token"]


def get_activity_details(activity_id: int):
    """
    Scarica i dettagli generali, inclusi i segmenti e il flag dei watt reali.
    """
    access_token = get_access_token()
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Errore recupero attività {activity_id}: {response.text}")
        return None
        
    return response.json()

def calcola_zone_potenza_reali(watt_array):
    # Inizializza i contatori dei secondi passati in ogni zona
    zone = {"Z1": 0, "Z2": 0, "Z3": 0, "Z4": 0, "Z5": 0,"Z6": 0,"Z7": 0}
    
    for watt in watt_array:
        if watt <= 114:
            zone["Z1"] += 1
        elif 114 < watt <= 155:
            zone["Z2"] += 1
        elif 155 < watt <= 186:
            zone["Z3"] += 1
        elif 186 <= watt <= 217:
            zone["Z4"] += 1
        elif 217 < watt >= 249:
            zone["Z5"] += 1
        elif 249 > watt <= 311:
            zone["Z6"] += 1
        elif watt > 311:
            zone["Z7"] += 1
            
    # Converte i secondi in minuti per una lettura più facile
    zone_minuti = {k: round(v / 60, 1) for k, v in zone.items()}
    return zone_minuti

def get_activity_zones(activity_id: int):
    """
    Scarica le zone di frequenza cardiaca dall'API standard 
    e calcola manualmente le zone di potenza reali dallo stream.
    """
    access_token = get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    
    zones_data = {"heartrate": [], "power": {}}
    
    # --- 1. RECUPERO ZONE CARDIO (Endpoint Standard) ---
    url_zones = f"https://www.strava.com/api/v3/activities/{activity_id}/zones"
    response_zones = requests.get(url_zones, headers=headers)
    
    if response_zones.status_code == 200:
        for metric in response_zones.json():
            # Prendiamo SOLO il cuore. Ignoriamo la potenza fittizia di Strava.
            if metric.get("type") == "heartrate":
                zones_data["heartrate"] = metric.get("distribution_buckets", [])
                
    # --- 2. CALCOLO ZONE POTENZA (Endpoint Streams) ---
    url_streams = f"https://www.strava.com/api/v3/activities/{activity_id}/streams?keys=watts&key_by_type=true"
    response_streams = requests.get(url_streams, headers=headers)
    
    if response_streams.status_code == 200:
        dati_stream = response_streams.json()
        
        # Controlliamo che l'attività abbia effettivamente i dati di potenza (es. se sei sui rulli)
        if "watts" in dati_stream:
            watt_array = dati_stream["watts"]["data"]
            zones_data["power"] = calcola_zone_potenza_reali(watt_array)
        else:
            print("Nessun dato di potenza trovato in questa attività (forse uscita solo outdoor senza misuratore?).")
            
    return zones_data


def format_strava_data_for_gemini(activity_id: int):
    """
    Formatta i dati per Gemini includendo potenza reale (se presente) e segmenti.
    """
    details = get_activity_details(activity_id)
    if not details:
        return None
        
    zones = get_activity_zones(activity_id)
    
    dati_puliti = {
        "strava_id": activity_id,
        "titolo": details.get("name"),
        "distanza_km": round(details.get("distance", 0) / 1000, 2),
        "dislivello_m": details.get("total_elevation_gain"),
        "tempo_movimento_minuti": round(details.get("moving_time", 0) / 60, 1),
        "fc_media": details.get("average_heartrate"),
        "fc_max": details.get("max_heartrate"),
        "sforzo_relativo": details.get("suffer_score", "Non disponibile"),
        "tempo_in_zone_cardio": [],
        "tempo_in_zone_potenza": [],
        "segmenti_rilevanti": []
    }
    
    # --- GESTIONE ZONE CARDIO ---
    for i, bucket in enumerate(zones.get("heartrate", [])):
        minuti = round(bucket.get("time", 0) / 60, 1)
        dati_puliti["tempo_in_zone_cardio"].append(f"Z{i+1}: {minuti} min")
        
    # --- GESTIONE ZONE POTENZA (Solo Reali) ---
    # Il flag device_watts garantisce che il dato arrivi da un power meter fisico
    if details.get("device_watts") is True:
        dati_puliti["potenza_media_w"] = details.get("average_watts")
        dati_puliti["potenza_max_w"] = details.get("max_watts")
        dati_puliti["potenza_normalizzata_w"] = details.get("weighted_average_watts")
        
        for i, bucket in enumerate(zones.get("power", [])):
            minuti = zones["power"][bucket]
            dati_puliti["tempo_in_zone_potenza"].append(f"{bucket} (Power): {minuti} min")
    else:
        dati_puliti["tempo_in_zone_potenza"] = "Nessun misuratore di potenza rilevato (dati stimati ignorati)."

    # --- GESTIONE SEGMENTI ---
    segment_efforts = details.get("segment_efforts", [])
    for effort in segment_efforts:
        nome_segmento = effort.get("name")
        tempo_secondi = effort.get("elapsed_time", 0)
        
        # Converte i secondi in un formato leggibile (es. "5m 30s")
        minuti, secondi = divmod(tempo_secondi, 60)
        tempo_formattato = f"{minuti}m {secondi}s"
        
        # Aggiungiamo un'icona se c'è un PR (Personal Record)
        pr_flag = ""
        for achievement in effort.get("achievements", []):
            if achievement.get("type_id") in [2, 3]: # 2 = PR, 3 = Top 10
                pr_flag = " 🏆 (PR!)"
                break
                
        dati_puliti["segmenti_rilevanti"].append(f"{nome_segmento}: {tempo_formattato}{pr_flag}")

    return dati_puliti


def get_latest_activity_id():
    """
    Interroga le API di Strava per ottenere l'ID dell'ultima attività registrata.
    """
    # NOTA: Sostituisci 'get_access_token()' con il nome effettivo 
    # della funzione che usi nel tuo file per ottenere il token valido.
    token = get_access_token() 
    
    url = "https://www.strava.com/api/v3/athlete/activities?per_page=1"
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        activities = response.json()
        if activities:
            return activities[0]["id"]
            
    print(f"Errore nel recupero attività: {response.text}")
    return None


def get_last_week_activities():
    today = datetime.now()
    
    dom = today - timedelta(days=today.weekday()+1)
    lun = dom - timedelta(days=6)
    token = get_access_token() 
    number_activites = 7  
    while True:  
         
        url = f"https://www.strava.com/api/v3/athlete/activities?per_page={number_activites}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = requests.get(url, headers=headers)
            activities = response.json() 
            last_date = activities[-1]["start_date_local"][:10] 
            
            if last_date < lun.strftime("%Y-%m-%d"):
                break
            else:
                number_activites += 1
        except Exception as e:
            print(e)
    i = len(activities) -1
    while i >= 0:
        if activities[i]["start_date_local"][:10] < lun.strftime("%Y-%m-%d"):
            activities.pop(i)
            i -= 1
        else:
            break
    attività_settimanali = []
    for activity in activities:
        dati_puliti = format_strava_data_for_gemini(activity["id"])
        attività_settimanali.append(dati_puliti)
    return attività_settimanali
def get_this_week_activities():
    today = datetime.now()
    lun = today - timedelta(days=today.weekday())
    dom = today + timedelta(days=6-today.weekday())
    
    token = get_access_token() 
    number_activites = 7
    while True:  
           
        url = f"https://www.strava.com/api/v3/athlete/activities?per_page={number_activites}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = requests.get(url, headers=headers)
            activities = response.json() 
            last_date = activities[-1]["start_date_local"][:10] 
            
            if last_date < lun.strftime("%Y-%m-%d"):
                break
            else:
                number_activites += 1
        except Exception as e:
            print(e)
    i = len(activities) -1
    while i >= 0:
        if activities[i]["start_date_local"][:10] < lun.strftime("%Y-%m-%d"):
            activities.pop(i)
            i -= 1
        else:
            break
    attività_settimanali = []
    for activity in activities:
        dati_puliti = format_strava_data_for_gemini(activity["id"])
        
        attività_settimanali.append(dati_puliti)
    return attività_settimanali