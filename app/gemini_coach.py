import json
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from datetime import datetime, timedelta

from pydantic import ValidationError
import app.database as db
import app.strava_client as strava
from app.models import FORMATO_DATA, PianoAllenamento
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

Non fare tabelle o elementi grafici, perché i messaggi vengono inviati su Telegram.
Regole per i feedback e i piani:
1. Analizza sempre il tempo speso nelle diverse zone (Z1-Z5).
2. Verifica se i segmenti hanno richiesto sforzi fuori soglia e come questo impatta il recupero.
3. Se noti deriva cardiaca (es. battiti alti a parità di sforzo prolungato), fallo notare.
4. Usa un tono professionale, diretto e motivante, adatto a un messaggio testuale (es. Telegram). Niente poemi, vai dritto al punto tecnico.
5. Per i giorni lavorativi usa degli allenamenti idonei al rullo e a zwift, facendo lavori usando il misuratore di potenza, mentre per il fine settimana pianifica allenamenti per uscite outdoor quindi senza misuratore di potenza
6. Varia e non fare lo stesso allenamento due volte consecutive
7. Per i lavori sui rulli fai sempre riferimento ad allenamenti secondo le zone di potenza

{testo_manuale}
"""

# Configurazione standard per abbassare la "fantasia" e aumentare la precisione analitica
config_base = types.GenerateContentConfig(
    system_instruction=istruzioni_di_sistema,
    temperature=0.4
)

# Configurazione per i piani: Gemini deve restituire un JSON conforme a PianoAllenamento.
# La struttura degli allenamenti è descritta dallo schema, non serve ripeterla nel prompt.
config_piano = types.GenerateContentConfig(
    system_instruction=istruzioni_di_sistema,
    temperature=0.4,
    response_mime_type="application/json",
    response_schema=PianoAllenamento,
)


def calcola_settimana_piano(data_inizio_str: str, oggi: datetime | None = None) -> int:
    """Calcola la settimana corrente del piano di allenamento.

    Args:
        data_inizio_str (str): Data di inizio piano nel formato "gg/mm/aaaa".
        oggi (datetime | None, optional): Data di riferimento. Defaults to now.

    Returns:
        int: Numero di settimana (1 = prima settimana). Valori <= 0 indicano
            che il piano non è ancora iniziato.

    Raises:
        ValueError: Se la data non è nel formato "gg/mm/aaaa".
    """
    data_inizio = datetime.strptime(data_inizio_str, FORMATO_DATA).date()
    oggi = (oggi or datetime.now()).date()
    # La divisione intera arrotonda verso -inf: i giorni prima dell'inizio danno <= 0
    return (oggi - data_inizio).days // 7 + 1


def _genera_piano_strutturato(prompt: str) -> PianoAllenamento | None:
    """Invia un prompt a Gemini e restituisce il piano già validato.

    Args:
        prompt (str): Richiesta da inviare al modello.

    Returns:
        PianoAllenamento | None: Piano conforme allo schema, oppure None se
            la chiamata fallisce o la risposta non rispetta lo schema.
    """
    try:
        inizio = datetime.now()
        print(f"🕒 {inizio.strftime('%d/%m/%Y, %H:%M:%S')}: Richiesta piano inviata a Gemini. Prompt:\n{prompt}")
        risposta = client.models.generate_content(
            model="gemini-pro-latest",
            contents=prompt,
            config=config_piano,
        )
        durata = (datetime.now() - inizio).total_seconds()
        print(f"✅ Risposta di Gemini ricevuta in {durata:.2f} secondi.")
        if risposta.usage_metadata:
            uso = risposta.usage_metadata
            print(
                f"📊 Consumo Token: {uso.prompt_token_count} (input) + "
                f"{uso.candidates_token_count} (output) = {uso.total_token_count} totali",
                flush=True,
            )

        # Con uno schema Pydantic l'SDK restituisce già l'oggetto in `parsed`;
        # se il parsing automatico fallisce, si valida il testo JSON a mano.
        if isinstance(risposta.parsed, PianoAllenamento):
            return risposta.parsed
        return PianoAllenamento.model_validate_json(risposta.text)

    except ValidationError as e:
        print(f"❌ {datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} - Piano non conforme allo schema: {e}")
    except Exception as e:
        print(f"❌ {datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} - ERRORE API GEMINI: {e}")
    return None

# 2. GENERATORE DI PIANI DI ALLENAMENTO
def genera_piano_allenamento(dati_utente: dict) -> PianoAllenamento | None:
    """Genera le prime due settimane del piano di allenamento.

    Args:
        dati_utente (dict): Profilo dell'atleta raccolto durante l'onboarding
            (obiettivo, timeline, giorni disponibili, zone HR, FTP, data inizio).

    Returns:
        PianoAllenamento | None: Commento del coach e allenamenti strutturati,
            oppure None se Gemini non risponde correttamente.
    """
    prompt = f"""
    Crea un piano di allenamento basato su queste specifiche:
    - Data inizio: {dati_utente.get("data inizio piano")}
    - Obiettivo principale: {dati_utente.get('obiettivo', 'Non specificato')}
    - Timeline/Scadenza: {dati_utente.get('timeline', 'Non specificata')}
    - Giorni a disposizione per allenarsi: {dati_utente.get('giorni_disponibili', 'Non specificati')}
    - Parametri Fisiologici:
        Zone HR: {dati_utente.get('zone_hr', 'Non specificate')}
        FTP: {dati_utente.get('ftp', 'Non disponibile')}

    Genera le prime due settimane a partire dalla data di inizio, giorno per giorno,
    inclusi i giorni di riposo: il piano verrà aggiornato ogni settimana.
    Distingui chiaramente le sessioni di qualità e i lunghi.
    Nel commento spiega in breve l'impostazione del piano.
    """
    return _genera_piano_strutturato(prompt)

# 3. RELAZIONE ULTIME USCITE
def analizza_uscite_settimanali(dati_strava_puliti:dict):
    prompt = """Fornisci un commento tecnico sull'esecuzione delle uscite di questa settimana, valutando il carico interno 
                (cuore) ed esterno (potenza/dislivello). Dimmi come questa uscita impatterà il recupero dei prossimi giorni. Analizza queste attivita nei massimi dettagli una per uno e fai un recap"""
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
                Uscita {uscite.get('titolo')} in data {uscite.get('Start time')}.
                
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
        return output
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
    L'atleta ha appena salvato una nuova uscita su Strava il {dati_strava_puliti.get("Start time")}. Analizza i seguenti dati:
    
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
        return response.text
    except Exception as e:
            # Registriamo l'errore tecnico nel log di Render per fare debug
            print(f"❌ {datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} - ERRORE API GEMINI: {e}")
            
            # Salviamo un messaggio discorsivo che Telegram può effettivamente inviare senza crashare
            response = "Mi dispiace, si è verificato un errore durante l'elaborazione dei tuoi dati. Riprova tra poco."
            
def aggiorna_piano(utente: dict, settimana: int) -> PianoAllenamento | None:
    """Ricalcola gli allenamenti della settimana corrente in base alle uscite fatte.

    Pensata per essere eseguita il lunedì: la settimana da pianificare va da
    oggi (lunedì) alla domenica successiva.

    Args:
        utente (dict): Documento utente da MongoDB (con ``chat_id`` e ``profilo``).
        settimana (int): Numero della settimana del piano che inizia oggi.

    Returns:
        PianoAllenamento | None: Feedback sulla settimana precedente e
            allenamenti della settimana corrente, oppure None in caso di errore.
    """
    profilo = utente["profilo"]
    piano_corrente = db.get_plan(utente["chat_id"])

    oggi = datetime.now().date()
    lunedi = oggi - timedelta(days=oggi.weekday())
    domenica = lunedi + timedelta(days=6)

    uscite_formattate = ""
    for uscita in strava.get_last_week_activities():
        uscite_formattate += f"""
            Uscita {uscita.get('titolo')} in data {uscita.get('Start time')}.

            - Distanza: {uscita.get('distanza_km')} km
            - Dislivello: {uscita.get('dislivello_m')} m
            - Tempo in movimento: {uscita.get('tempo_movimento_minuti')} minuti
            - Frequenza Cardiaca: Media {uscita.get('fc_media')} bpm | Max {uscita.get('fc_max')} bpm
            - Sforzo Relativo (Strava): {uscita.get('sforzo_relativo')}

            Distribuzione Zone Cardio:
            {uscita.get('tempo_in_zone_cardio')}

            Distribuzione Zone Potenza:
            {uscita.get('tempo_in_zone_potenza')}

            Segmenti rilevanti affrontati:
            {uscita.get('segmenti_rilevanti')}

            ###################################
            """

    prompt = f"""
        Dati dell'atleta:
        Obiettivo: {profilo.get("obiettivo")}
        Data finale: {profilo.get("timeline")}
        Giorni disponibili: {profilo.get("giorni_disponibili")}
        Zone HR: {profilo.get("zone_hr")}
        FTP: {profilo.get("ftp")}

        Piano corrente (JSON):
        {json.dumps(piano_corrente, ensure_ascii=False, indent=2)}

        Uscite effettivamente svolte nella settimana {settimana - 1}:
        {uscite_formattate or "Nessuna uscita registrata."}

        Oggi inizia la settimana {settimana}, dal {lunedi.strftime(FORMATO_DATA)}
        al {domenica.strftime(FORMATO_DATA)}.
        Confronta le uscite svolte con il piano e, in base ai risultati, all'obiettivo
        e al profilo dell'atleta, crea gli allenamenti di ogni giorno di questa settimana
        (inclusi i riposi), adattandoli se serve.
        Nel commento dai un feedback tecnico sulla settimana {settimana - 1}.
    """
    return _genera_piano_strutturato(prompt)