from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator
 
#: Formato delle date usato in tutto il piano (es. "27/10/2026").
FORMATO_DATA = "%d/%m/%Y"

GIORNI_SETTIMANA = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
 
#: Icone mostrate su Telegram in base allo sport dell'allenamento.
ICONE_SPORT = {"ciclismo": "🚴", "riposo": "😴"}

class Allenamento(BaseModel):
    """Singolo allenamento (o giorno di riposo) del piano.
 
    Le descrizioni dei campi vengono inviate a Gemini insieme allo schema
    e funzionano da istruzioni di formato.
 
    Attributes:
        id (int): Numero progressivo dell'allenamento nel piano.
        data (str): Data dell'allenamento nel formato "gg/mm/aaaa".
        sport (str): Sport praticato, oppure "Riposo" per i giorni di recupero.
        titolo (str): Nome breve della sessione.
        durata_minuti (int): Durata totale prevista, in minuti.
        dettaglio (str): Struttura completa della sessione.
    """
    
    id: int = Field(description="Numero progressivo dell'allenamento, da 1 in poi.")
    data: str = Field(description="Data dell'allenamento nel formato gg/mm/aaaa.")
    sport: str = Field(
        description=(
            "Sport dell'allenamento, es. 'Ciclismo', 'Corsa', 'Palestra'. "
            "Usa 'Riposo' per i giorni di recupero."
        )
    )
    titolo: str = Field(description="Nome breve della sessione, es. 'Sweet spot 3x10'.")
    durata_minuti: int = Field(description="Durata totale prevista in minuti (0 per il riposo).")
    dettaglio: str = Field(
        description=(
            "Struttura completa della sessione: riscaldamento, blocchi di lavoro con "
            "zone di potenza o cardio e durate, recuperi, defaticamento. Indica i "
            "minuti per ciascuna zona. Testo semplice, senza tabelle né Markdown."
        )
    )
    
    
    @field_validator("data")
    @classmethod
    def valida_data(cls, valore: str) -> str:
        """Verifica che la data sia nel formato "gg/mm/aaaa".
 
        Args:
            valore (str): Data restituita da Gemini.
 
        Returns:
            str: La data, invariata.
 
        Raises:
            ValueError: Se la data non rispetta il formato atteso.
        """
        datetime.strptime(valore, FORMATO_DATA)
        return valore
 
    @property
    def giorno(self) -> date:
        """date: Data dell'allenamento convertita in oggetto ``date``."""
        return datetime.strptime(self.data, FORMATO_DATA).date()
 
 
class PianoAllenamento(BaseModel):
    """Risposta completa di Gemini quando genera o aggiorna un piano.
 
    Attributes:
        commento (str): Note del coach (impostazione del piano o feedback
            sulla settimana appena conclusa).
        allenamenti (list[Allenamento]): Allenamenti in ordine cronologico.
    """
 
    commento: str = Field(
        description=(
            "Commento del coach: impostazione generale del piano oppure feedback "
            "sulla settimana precedente. Testo semplice, conciso, senza Markdown."
        )
    )
    allenamenti: list[Allenamento] = Field(
        description="Allenamenti e giorni di riposo, uno per giorno, in ordine cronologico."
    )
 
 
def formatta_allenamento(allenamento: Allenamento) -> str:
    """Trasforma un allenamento in un blocco di testo leggibile su Telegram.
 
    Args:
        allenamento (Allenamento): Allenamento da formattare.
 
    Returns:
        str: Testo semplice, ad esempio::
 
            🚴 #3 · Mar 27/10/2026 · Sweet spot 3x10 (60')
            Riscaldamento 10' Z1-Z2 ...
    """
    giorno = GIORNI_SETTIMANA[allenamento.giorno.weekday()]
    icona = ICONE_SPORT.get(allenamento.sport.strip().lower(), "🏋️")
    durata = f" ({allenamento.durata_minuti}')" if allenamento.durata_minuti else ""
 
    intestazione = f"{icona} #{allenamento.id} · {giorno} {allenamento.data} · {allenamento.titolo}{durata}"
    return f"{intestazione}\n{allenamento.dettaglio.strip()}"
 
 
def formatta_piano(allenamenti: list[Allenamento | dict]) -> str:
    """Trasforma una lista di allenamenti nel testo del piano per Telegram.
 
    Accetta sia oggetti ``Allenamento`` sia dizionari letti da MongoDB;
    i dizionari vengono validati e convertiti prima della formattazione.
 
    Args:
        allenamenti (list[Allenamento | dict]): Allenamenti da mostrare.
 
    Returns:
        str: Allenamenti separati da una riga vuota, in ordine cronologico.
            Stringa vuota se la lista è vuota.
    """
    modelli = [
        a if isinstance(a, Allenamento) else Allenamento.model_validate(a)
        for a in allenamenti
    ]
    modelli.sort(key=lambda a: a.giorno)
    return "\n\n".join(formatta_allenamento(a) for a in modelli)