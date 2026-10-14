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


def get_activity_zones(activity_id: int):
    """
    Scarica le zone sia di frequenza cardiaca che di potenza.
    """
    access_token = get_access_token()
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/zones"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    response = requests.get(url, headers=headers)
    
    zones_data = {"heartrate": [], "power": []}
    
    if response.status_code == 200:
        for metric in response.json():
            if metric.get("type") == "heartrate":
                zones_data["heartrate"] = metric.get("distribution_buckets", [])
            elif metric.get("type") == "power":
                zones_data["power"] = metric.get("distribution_buckets", [])
                
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
            minuti = round(bucket.get("time", 0) / 60, 1)
            dati_puliti["tempo_in_zone_potenza"].append(f"Z{i+1} (Power): {minuti} min")
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
    while True:  
        number_activites = 7   
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
        zones = get_activity_zones(activity["id"])
        dati_puliti = {
                "titolo": activity.get("name"),
                "data": activity.get("start_date_local")[:10],
                "distanza_km": round(activity.get("distance", 0) / 1000, 2),
                "dislivello_m": activity.get("total_elevation_gain"),
                "tempo_movimento_minuti": round(activity.get("moving_time", 0) / 60, 1),
                "fc_media": activity.get("average_heartrate"),
                "fc_max": activity.get("max_heartrate"),
                "sforzo_relativo": activity.get("suffer_score", "Non disponibile"),
                "tempo_in_zone_cardio": [],
                "tempo_in_zone_potenza": [],
                "segmenti_rilevanti": []
            }
        for i, bucket in enumerate(zones.get("heartrate", [])):
            minuti = round(bucket.get("time", 0) / 60, 1)
            dati_puliti["tempo_in_zone_cardio"].append(f"Z{i+1}: {minuti} min")
        if activity.get("device_watts") is True:
            dati_puliti["potenza_media_w"] = activity.get("average_watts")
            dati_puliti["potenza_max_w"] = activity.get("max_watts")
            dati_puliti["potenza_normalizzata_w"] = activity.get("weighted_average_watts")
            
            for i, bucket in enumerate(zones.get("power", [])):
                minuti = round(bucket.get("time", 0) / 60, 1)
                dati_puliti["tempo_in_zone_potenza"].append(f"Z{i+1} (Power): {minuti} min")
        else:
            dati_puliti["tempo_in_zone_potenza"] = "Nessun misuratore di potenza rilevato (dati stimati ignorati)."
        
        # --- GESTIONE SEGMENTI ---
        segment_efforts = activity.get("segment_efforts", [])
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
        attività_settimanali.append(dati_puliti)
    return attività_settimanali
def get_this_week_activities():
    today = datetime.now()
    lun = today - timedelta(days=today.weekday())
    dom = today + timedelta(days=6-today.weekday())
    
    token = get_access_token() 
    while True:  
        number_activites = 7   
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
        zones = get_activity_zones(activity["id"])
        dati_puliti = {
                "titolo": activity.get("name"),
                "data": activity.get("start_date_local")[:10],
                "distanza_km": round(activity.get("distance", 0) / 1000, 2),
                "dislivello_m": activity.get("total_elevation_gain"),
                "tempo_movimento_minuti": round(activity.get("moving_time", 0) / 60, 1),
                "fc_media": activity.get("average_heartrate"),
                "fc_max": activity.get("max_heartrate"),
                "sforzo_relativo": activity.get("suffer_score", "Non disponibile"),
                "tempo_in_zone_cardio": [],
                "tempo_in_zone_potenza": [],
                "segmenti_rilevanti": []
            }
        for i, bucket in enumerate(zones.get("heartrate", [])):
            minuti = round(bucket.get("time", 0) / 60, 1)
            dati_puliti["tempo_in_zone_cardio"].append(f"Z{i+1}: {minuti} min")
        if activity.get("device_watts") is True:
            dati_puliti["potenza_media_w"] = activity.get("average_watts")
            dati_puliti["potenza_max_w"] = activity.get("max_watts")
            dati_puliti["potenza_normalizzata_w"] = activity.get("weighted_average_watts")
            
            for i, bucket in enumerate(zones.get("power", [])):
                minuti = round(bucket.get("time", 0) / 60, 1)
                dati_puliti["tempo_in_zone_potenza"].append(f"Z{i+1} (Power): {minuti} min")
        else:
            dati_puliti["tempo_in_zone_potenza"] = "Nessun misuratore di potenza rilevato (dati stimati ignorati)."
        
        # --- GESTIONE SEGMENTI ---
        segment_efforts = activity.get("segment_efforts", [])
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
        attività_settimanali.append(dati_puliti)
    return attività_settimanali