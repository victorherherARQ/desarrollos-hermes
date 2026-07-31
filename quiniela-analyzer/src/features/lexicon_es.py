"""Spanish sentiment lexicon for football news scoring.

200+ words covering positive and negative football-related sentiment.
Score range: [-1.0, +1.0] where positive = good form, negative = bad form.
"""
from __future__ import annotations

# Positive football words (sorted)
POSITIVE_WORDS: set[str] = {
    # Victory / winning
    "victoria", "victorias", "gana", "ganado", "ganar", "ganador",
    "triunfo", "triunfos", "blanco", "blancos",  # Real Madrid "los blancos"
    "pizza",  # Aragonés style
    "goleada", "goleadas", "festín", "festivales",
    "liderato", "líder", "lider", "lideres", "liderazgo",
    "champion", "campeón", "campeones", "campeonato", "campions",
    "superioridad", "dominio", "dominador",

    # Positive emotions / performance
    "heroico", "heroica", "espléndido", "esplendida", "esplendor",
    "excelente", "excelentes", "extraordinario", "extraordinaria",
    "brillante", "brillantes", "brillo", "magnifico", "magnifica",
    "espectacular", "espectaculares", "impresionante", "impresionantes",
    "asombroso", "asombrosa", "genial", "geniales",
    "fantástico", "fantastico", "fantastica", "increible", "increíble",
    "memorable", "inolvidable", "inolvidables",
    "-orgullo", " Orgullo", "orgullosos", "orgullosa",

    # Form / momentum
    "buena racha", "buena racha", "racha", "rachas",
    "buen momento", "en buena forma", "en forma",
    "ascenso", "ascensos", "ascendido", "ascender",
    "fiesta", "fiestas", "celebración", "celebraciones",
    "euforia", "euforico", "euforica",

    # Praise
    "crack", "cracks", " Crack", " Crack",
    "estrella", "estrellas", " cracks", " crack",
    "referente", "referentes", "figura", "figuras",
    "talento", "talentos", "talENTO", "talentoso",
    "cr7", "messi",  # star players - associated with their team success

    # Goal related
    "gol", "goles", "anotación", "anotaciones",
    "mete", "metido", "marca", "marcar", "marcador",
    "remate", "remates", "tiro", "tiros", "disparo", "disparos",
    "biricu", "biriqui",  # childhood celebrations

    # Defensive excellence
    "cercano", "cercana", "inmarcable", "inmaculado",
    "porta", "cierrapuertas", "零封",  # clean sheet
    "clean", "cleansheet", "cleansheets",

    # Coach / tactical
    "gaFFER", "gaffer", "entrenador", "entrenadores",
    "proye", "projection", "plantilla", "plantillas",
    "fichaje", "fichajes", "refuerzo", "refuerzos",
    "insignia", "insignias", "leyenda", "leyendas",

    # Passion / fans
    "afición", "aficion", "aficiones", "pasión", "pasion",
    "anim", "animo", "ánimo", "animame", "coraje",
    "grada", "gradas", " Estadio", "estadio",
    "hincha", "hinchas", "cule", "cules", "madridismo",
    "sevillismo", "betismo", "athleticz", "球迷",

    # Recovery / resilience
    "remontada", "remontadas", "revancha", "rescate",
    "resiliencia", "fuerte", "fortaleza", "fuerza",

    # Future / hope
    "esperanza", "esperanzas", "ilusión", "ilusion",
    "ilusiones", "nuevos", "nuevas", "positivo", "positivos",
    "progreso", "progresos", "mejora", "mejoras",
}

# Negative football words (sorted)
NEGATIVE_WORDS: set[str] = {
    # Loss / defeat
    "derrota", "derrotas", "derrotado", "derrotados",
    "pierde", "pierdo", "perdido", "perder", "perdido",
    "fracaso", "fracasos", "fail", "failure",
    "humillación", "humillacion", "humillaciones",
    "bochorno", "bochornoso", "vergüenza", "verguenza",
    "desastre", "desastres", "desastroso", "desastrosa",
    "pésimo", "pesimo", "pesima", "pésima",

    # Poor performance
    "mal", "malo", "malos", "mala", "malas",
    "terrible", "terribles", "espantoso", "espantosa",
    "atroz", "atroces", "decepcionante", "decepcionantes",
    "decepción", "decepcion", "frustración", "frustracion",
    "indign", "indigno", "indigna", "indignos",
    "lamentable", "lamentables", "patético", "patetico",
    "patetica", "penoso", "penosa", "penoses",
    "inaceptable", "inaceptables", "vergonzoso", "vergonzosa",

    # Crisis / problems
    "crisis", " CRISIS", "caos", "caótico", "caotico",
    "problema", "problemas", "problemón", "problemote",
    "conflicto", "conflictos", "trama", "tramas",
    "roubo", "robo", "robo clamoroso", "scandal", "escandalo",
    "escandalazo", "polemica", "polémica", "polémicas",
    "bronca", "bronce", "cabreo", "cuelgue",

    # Financial / institutional
    "deuda", "deudas", "endeudado", "endeudamiento",
    "crash", "bancarrota", "quiebra", "suspenso",
    "expuls", "expulsado", "expulsados", "expulsion",
    "sancion", "sanción", "sanciones", "multa", "multas",
    "demanda", "demandas", "juicio", "juicios",

    # Descent / relegation
    "descenso", "descensos", "desciende", "descender",
    "relegación", "relegacion", " Liga", "liga de segunda",
    "segunda división", "segunda", "bajon", "bajón",
    "caida", "caída", "caidas", "caídas",

    # Negative momentum
    "racha negativa", "racha terrible", "sin ganar",
    "sin victoria", "sin gol", "sin anotar",
    "empate", "empates", "tablas",  # draws are neutral slightly neg

    # Injury / absence
    "lesión", "lesion", "lesiones", "lesionado", "lesionados",
    "tocado", "tocada", "baja", "bajas", "bajón",
    "herido", "heridos", "fractura", "fracturas",
    "operación", "operacion", "cirugía", "cirugia",

    # Negative fans / atmosphere
    "pitar", "pitada", "pitadas", "abucheo", "abucheos",
    "abucheado", "protesta", "protestas", "queja", "quejas",
    "desaprobación", "desaprobacion", "disconformidad",
    "indisciplina", "indisciplinado", "bulbar", "bufon",

    # Referee / VAR controversy (neutral-negative)
    " VAR ", "争议", "penalti", "penalti mal pitado",
    "arbitral", "arbitrage", "corne", "cuerno",

    # Coach / player criticism
    "cese", "cesado", "destitución", "destitucion",
    "destituido", "echado", "despedido", "despedida",
    "mala gestión", "mal gestion", "malentendido",
    "culpa", "culpado", "culpables", "culpable",
    "debacle", "descalific", "inutil", "inútiles",

    # Negative future
    "incertidumbre", "incierto", "incierta",
    "desconfianza", "duda", "dudas", "incertidumbres",
    "peor", "peores", "fatal", "catastrofe",
}


def get_sentiment_score(text: str) -> tuple[int, int, float]:
    """Score a text using the Spanish football lexicon.

    Returns (n_positive, n_negative, score)
    where score = (pos - neg) / max(1, pos + neg) in [-1, 1]
    """
    words = set(text.lower().split())
    pos = sum(1 for w in POSITIVE_WORDS if w in words)
    neg = sum(1 for w in NEGATIVE_WORDS if w in words)
    total = pos + neg
    score = (pos - neg) / max(1, total)
    return pos, neg, score


def score_headline(headline: str) -> float:
    """Return sentiment score for a single headline in [-1, 1]."""
    _, _, score = get_sentiment_score(headline)
    return score
