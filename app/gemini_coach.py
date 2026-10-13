import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Carica le variabili d'ambiente (inclusa GEMINI_API_KEY)
load_dotenv()

testo_manuale = ''
# Caricamento manuale allenamento
try:
    with open("Manuale_potenza.txt", 'r', encoding='utf-8') as f:
        testo_manuale = f.read()
except FileNotFoundError:
    print("⚠️ File manuale_potenza.txt non trovato. Il coach procederà senza.")

try:
    with open("info_personali.txt", 'r', encoding='utf-8') as f:
        info_personali = f.read()
except FileNotFoundError:
    print("⚠️ info_personali.txt non trovato. Il coach procederà senza.")

# Recupera esplicitamente la chiave e inizializza il client
chiave_api = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=chiave_api)

# 1. L'IDENTITÀ DELL'AGENTE E IL PROFILO ATLETA
istruzioni_di_sistema = f"""
Sei un preparatore atletico d'élite specializzato nel ciclismo su strada e data-driven.
{info_personali}
Regole per i feedback e i piani:
1. Analizza sempre il tempo speso nelle diverse zone (Z1-Z5).
2. Verifica se i segmenti hanno richiesto sforzi fuori soglia e come questo impatta il recupero.
3. Se noti deriva cardiaca (es. battiti alti a parità di sforzo prolungato), fallo notare.
4. Usa un tono professionale, diretto e motivante, adatto a un messaggio testuale (es. Telegram). Niente poemi, vai dritto al punto tecnico.
5. Per i giorni lavorativi usa degli allenamenti idoneei al rullo e a zwift, facendo lavori usando il misuratore di potenza, mentre per il fine settimana pianifica allenamenti per uscite outdoor quindi senza misuratore di potenza
6. Varia e non fare lo stesso allenamento due volte consecutive
7. Per i lavori sui rulli fai sempre riferimento ad allenamenti secondo le zone di potenza



{testo_manuale}
"""

# Configurazione standard per abbassare la "fantasia" e aumentare la precisione analitica
config_base = types.GenerateContentConfig(
    system_instruction=istruzioni_di_sistema,
    temperature=0.4
)

# 2. GENERATORE DI PIANI DI ALLENAMENTO
def genera_piano_allenamento(dati_utente: dict):
    """
    Riceve i parametri dell'atleta e genera un piano di 2 settimane.
    """
    prompt = f"""
    Crea un piano di allenamento aggiornato basato su queste specifiche:
    - Obiettivo principale: {dati_utente.get('obiettivo', 'Non specificato')}
    - Timeline/Scadenza: {dati_utente.get('timeline', 'Non specificata')}
    - Giorni a disposizione per allenarsi: {dati_utente.get('giorni_disponibili', 'Non specificati')}
    - Parametri Fisiologici: 
        Zone HR: {dati_utente.get('zone_hr', 'Non specificate')}
        FTP: {dati_utente.get('ftp', 'Non disponibile')}
    
    Genera un programma strutturato giorno per giorno. Evidenzia chiaramente i giorni di riposo, 
    le sessioni di qualità e i lunghi. Specifica i minuti da passare in ciascuna zona.
    """
    return prompt
    response = client.models.generate_content(
        model='gemini-flash-latest',
        contents=prompt,
        config=config_base
    )
    return response.text

# 3. CRITICO DELLE PRESTAZIONI POST-ALLENAMENTO
def analizza_uscita(dati_strava_puliti: dict):
    """
    Prende il dizionario formattato da strava_client.py e restituisce l'analisi tecnica.
    """
    prompt = f"""
    L'atleta ha appena salvato una nuova uscita su Strava. Analizza i seguenti dati:
    
    - Titolo attività: {dati_strava_puliti.get('titolo')}
    - Distanza: {dati_strava_puliti.get('distanza_km')} km
    - Dislivello: {dati_strava_puliti.get('dislivello_m')} m
    - Tempo in movimento: {dati_strava_puliti.get('tempo_movimento_minuti')} minuti
    - Frequenza Cardiaca: Media {dati_strava_puliti.get('fc_media')} bpm | Max {dati_strava_puliti.get('fc_max')} bpm
    - Sforzo Relativo (Strava): {dati_strava_puliti.get('sforzo_relativo')}
    
    Distribuzione Zone Cardio:
    {dati_strava_puliti.get('tempo_in_zone_cardio')}
    
    Distribuzione Zone Potenza:
    {dati_strava_puliti.get('tempo_in_zone_potenza')}
    
    Segmenti rilevanti affrontati:
    {dati_strava_puliti.get('segmenti_rilevanti')}
    
    Fornisci un commento tecnico sull'esecuzione di questa uscita, valutando il carico interno 
    (cuore) ed esterno (potenza/dislivello). Dimmi come questa uscita impatterà il recupero dei prossimi giorni.
    """
    response = client.models.generate_content(
        model='gemini-flash-latest',
        contents=prompt,
        config=config_base
    )
    return response.text