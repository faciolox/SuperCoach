import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from datetime import datetime,date
import app.database as db
import app.strava_client as strava
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
    - Data inizio: {dati_utente.get("data inizio piano")}
    - Obiettivo principale: {dati_utente.get('obiettivo', 'Non specificato')}
    - Timeline/Scadenza: {dati_utente.get('timeline', 'Non specificata')}
    - Giorni a disposizione per allenarsi: {dati_utente.get('giorni_disponibili', 'Non specificati')}
    - Parametri Fisiologici: 
        Zone HR: {dati_utente.get('zone_hr', 'Non specificate')}
        FTP: {dati_utente.get('ftp', 'Non disponibile')}
    
    Genera un programma strutturato giorno per giorno. Evidenzia chiaramente i giorni di riposo, 
    le sessioni di qualità e i lunghi. Specifica i minuti da passare in ciascuna zona.
    """
    
    try:
        now = datetime.now()
        print(f"🕒 {now.strftime("%d/%m/%Y, %H:%M:%S")}: Richiesta API inviata a Gemini. Prompt:\n{prompt}")
        # LA CHIAMATA A GEMINI DEVE STARE QUI DENTRO
        risposta_gemini = client.models.generate_content(
            model='gemini-pro-latest', # o il modello che usi
            contents=prompt,
            config=config_base
        )
        now2 = datetime.now()
        time_delta = (now2-now).total_seconds()
        print(f"✅ {now2.strftime('%d/%m/%Y, %H:%M:%S')}: Risposta elaborata con successo in {time_delta:.2f} secondi.")
        if risposta_gemini.usage_metadata:
            token_in = risposta_gemini.usage_metadata.prompt_token_count
            token_out = risposta_gemini.usage_metadata.candidates_token_count
            token_totali = risposta_gemini.usage_metadata.total_token_count
            print(f"📊 Consumo Token: {token_in} (input) + {token_out} (output) = {token_totali} totali", flush=True)
        
        # Estraiamo il testo pulito per Telegram
        response = risposta_gemini.text
        
    except Exception as e:
        # Registriamo l'errore tecnico nel log di Render per fare debug
        print(f"❌ {datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} - ERRORE API GEMINI: {e}")
        
        # Salviamo un messaggio discorsivo che Telegram può effettivamente inviare senza crashare
        response = "Mi dispiace, si è verificato un errore durante l'elaborazione dei tuoi dati. Riprova tra poco."
    return response

# 3. RELAZIONE ULTIME USCITE
def analizza_uscite_settimanali(dati_strava_puliti:dict):
    prompt = """Fornisci un commento tecnico sull'esecuzione delle uscite di questa settimana, valutando il carico interno 
                (cuore) ed esterno (potenza/dislivello). Dimmi come questa uscita impatterà il recupero dei prossimi giorni."""
    output = ""
    for uscite in dati_strava_puliti:
        try:
            uscita = db.get_activity("",uscite['strava_id'])
        except Exception as e:
            print(e)
        if uscita:
            output += uscita.get("messaggio")
        else: 
            prompt += f"""\n
                Uscita {uscite.get('titolo')} in data {uscite.get('data')}. Analizza i seguenti dati:
                
                - Titolo attività: {uscite.get('titolo')}
                - Distanza: {uscite.get('distanza_km')} km
                - Dislivello: {uscite.get('dislivello_m')} m
                - Tempo in movimento: {uscite.get('tempo_movimento_minuti')} minuti
                - Frequenza Cardiaca: Media {uscite.get('fc_media')} bpm | Max {uscite.get('fc_max')} bpm
                - Sforzo Relativo (Strava): {uscite.get('sforzo_relativo')}
                
                Distribuzione Zone Cardio:
                {uscite.get('tempo_in_zone_cardio')}
                
                Distribuzione Zone Potenza:
                {uscite.get('tempo_in_zone_potenza')}
                
                Segmenti rilevanti affrontati:
                {uscite.get('segmenti_rilevanti')}
                
                ###################################
                """
    try: 
        now = datetime.now()
        print(f"🕒 {now.strftime("%d/%m/%Y, %H:%M:%S")}: Richiesta API inviata a Gemini. Prompt:\n{prompt}")
        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents=prompt,
            config=config_base
        )
        now2 = datetime.now()
        time_delta = (now2-now).total_seconds()
        print(f"✅ {now2.strftime('%d/%m/%Y, %H:%M:%S')}: Risposta elaborata con successo in {time_delta:.2f}.")
        if response.usage_metadata:
            token_in = response.usage_metadata.prompt_token_count
            token_out = response.usage_metadata.candidates_token_count
            token_totali = response.usage_metadata.total_token_count
            print(f"📊 Consumo Token: {token_in} (input) + {token_out} (output) = {token_totali} totali", flush=True)
        output += response.text
        return response.text
    except Exception as e:
            # Registriamo l'errore tecnico nel log di Render per fare debug
            print(f"❌ {datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} - ERRORE API GEMINI: {e}")
            
            # Salviamo un messaggio discorsivo che Telegram può effettivamente inviare senza crashare
            response = "Mi dispiace, si è verificato un errore durante l'elaborazione dei tuoi dati. Riprova tra poco."
# 4. CRITICO DELLE PRESTAZIONI POST-ALLENAMENTO
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
    try: 
        now = datetime.now()
        print(f"🕒 {now.strftime("%d/%m/%Y, %H:%M:%S")}: Richiesta API inviata a Gemini. Prompt:\n{prompt}")
        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents=prompt,
            config=config_base
        )
        now2 = datetime.now()
        time_delta = (now2-now).total_seconds()
        print(f"✅ {now2.strftime('%d/%m/%Y, %H:%M:%S')}: Risposta elaborata con successo in {time_delta:.2f}.")
        if response.usage_metadata:
            token_in = response.usage_metadata.prompt_token_count
            token_out = response.usage_metadata.candidates_token_count
            token_totali = response.usage_metadata.total_token_count
            print(f"📊 Consumo Token: {token_in} (input) + {token_out} (output) = {token_totali} totali", flush=True)
            db.save_activity("",dati_strava_puliti["strava_id"], prompt, response.text)
        return response.text
    except Exception as e:
            # Registriamo l'errore tecnico nel log di Render per fare debug
            print(f"❌ {datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} - ERRORE API GEMINI: {e}")
            
            # Salviamo un messaggio discorsivo che Telegram può effettivamente inviare senza crashare
            response = "Mi dispiace, si è verificato un errore durante l'elaborazione dei tuoi dati. Riprova tra poco."
            
def aggiorna_piano(utente_aggiornato):
    profilo = utente_aggiornato["profilo"]
    data_inizio = datetime.strptime(profilo.get("data inizio piano"),"%d/%m/%Y")
    oggi = datetime.now()
    delta = data_inizio - oggi
    week = int(delta.days/7) +1
    
    #troviamo le uscite settimanali
    uscite_settimanali = strava.get_last_week_activities()
    uscite_formattate = ""
    for uscite in uscite_settimanali:
        uscite_formattate += f"""\n
            Uscita {uscite.get('titolo')} in data {uscite.get('data')}.
            
            - Titolo attività: {uscite.get('titolo')}
            - Distanza: {uscite.get('distanza_km')} km
            - Dislivello: {uscite.get('dislivello_m')} m
            - Tempo in movimento: {uscite.get('tempo_movimento_minuti')} minuti
            - Frequenza Cardiaca: Media {uscite.get('fc_media')} bpm | Max {uscite.get('fc_max')} bpm
            - Sforzo Relativo (Strava): {uscite.get('sforzo_relativo')}
            
            Distribuzione Zone Cardio:
            {uscite.get('tempo_in_zone_cardio')}
            
            Distribuzione Zone Potenza:
            {uscite.get('tempo_in_zone_potenza')}
            
            Segmenti rilevanti affrontati:
            {uscite.get('segmenti_rilevanti')}
            
            ###################################
            """
    prompt = f"""
        Aggiorna il piano per la prossima settimana fornendo dettagliatamente tutti gli allenamenti dal lunedi alla domenica.
        Di seguito ti ricordo i dati:
        Obiettivo: {profilo.get("obiettivo")}
        Data finale {profilo.get("timeline")}
        Giorni disponibili: {profilo.get("giorni_disponibili")}
        Zone HR: {profilo.get("zone_hr")}
        FTP: {profilo.get("ftp")}
        
        Queste sono le uscite della settimana {week - 1}
        {uscite_formattate}
        
        Oggi siamo alla settimana {week}.
        
        Questo è il piano corrente:
        {profilo.get("piano_corrente")}
        
        In base ai risultati degli alleamenti di questa settimana, al proseguo dell'allenamento, e ai dati inziali del profilo dell'atleta
        regola gli allenamenti (se c'è bisogno) della settimana {week}
    """
    risposta_gemini = "ciao"
    try:
            now = datetime.now()
            print(f"🕒 {now.strftime("%d/%m/%Y, %H:%M:%S")}: Richiesta API inviata a Gemini. Prompt:\n{prompt}")
            # LA CHIAMATA A GEMINI DEVE STARE QUI DENTRO
            risposta_gemini = client.models.generate_content(
                model='gemini-pro-latest', # o il modello che usi
                contents=prompt,
                config=config_base
            )
            now2 = datetime.now()
            time_delta = (now2-now).total_seconds()
            print(f"✅ {now2.strftime('%d/%m/%Y, %H:%M:%S')}: Risposta elaborata con successo in {time_delta:.2f} secondi.")
            if risposta_gemini.usage_metadata:
                token_in = risposta_gemini.usage_metadata.prompt_token_count
                token_out = risposta_gemini.usage_metadata.candidates_token_count
                token_totali = risposta_gemini.usage_metadata.total_token_count
                print(f"📊 Consumo Token: {token_in} (input) + {token_out} (output) = {token_totali} totali", flush=True)
            
            # Estraiamo il testo pulito per Telegram
            response = risposta_gemini.text
            
    except Exception as e:
        # Registriamo l'errore tecnico nel log di Render per fare debug
        print(f"❌ {datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} - ERRORE API GEMINI: {e}")
        
        # Salviamo un messaggio discorsivo che Telegram può effettivamente inviare senza crashare
        response = "Mi dispiace, si è verificato un errore durante l'elaborazione dei tuoi dati. Riprova tra poco."
    return response
    
