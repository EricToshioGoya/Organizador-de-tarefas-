"""Constantes do domínio (atributos da seção 2.2, fases, motivos de adiamento, pontos)."""

TITLE_MAX = 120
NAME_MAX = 60
TEXT_MAX = 20_000
COMMENT_MAX = 5_000
STEP_MAX = 500
URL_MAX = 2_000

# Status da tarefa (seção 3)
PENDING = "pendente"
DONE = "concluida"
TASK_STATUSES = (PENDING, DONE)

# Status da meta (RN15)
GOAL_ACTIVE = "andamento"
GOAL_DONE = "concluida"

# Dificuldade (2.2) e pontos (RN24)
DIFFICULTIES = ("facil", "medio", "dificil")
DEFAULT_DIFFICULTY = "medio"
DIFFICULTY_LABELS = {"facil": "Fácil", "medio": "Médio", "dificil": "Difícil"}
DIFFICULTY_POINTS = {"facil": 1, "medio": 2, "dificil": 3}

# Fases (RF57, RN31)
PHASES = ("planejamento", "producao", "alpha", "beta", "concluido")
DEFAULT_PHASE = "planejamento"
PHASE_LABELS = {
    "planejamento": "Planejamento",
    "producao": "Em produção",
    "alpha": "Versão alpha",
    "beta": "Versão beta (funcionando)",
    "concluido": "Totalmente concluído",
}

# Perfis de conta (RF61)
ROLE_MEMBER = "membro"
ROLE_MANAGER = "gestor"
ROLES = (ROLE_MEMBER, ROLE_MANAGER)

# Motivos de adiamento (RF47)
POSTPONE_REASONS = {
    "subestimei": "Subestimei o esforço",
    "prioridade": "Mudança de prioridade",
    "dependencia": "Dependência de outra pessoa",
    "outro": "Outro",
}

# Tarefa parada (RN22)
DEFAULT_STALE_DAYS = 5

# Cores de avatar (RF25): identificam a conta; a interface as exibe em tom pastel, com iniciais escuras.
ACCOUNT_COLORS = (
    "#22D3EE",  # ciano
    "#A78BFA",  # violeta
    "#F472B6",  # rosa
    "#34D399",  # verde
    "#FBBF24",  # âmbar
    "#60A5FA",  # azul
    "#FB923C",  # laranja
    "#2DD4BF",  # turquesa
    "#C084FC",  # lilás
    "#A3E635",  # lima
    "#F87171",  # vermelho
    "#E879F9",  # magenta
)

PERIODS = ("7d", "30d", "90d", "12m", "all")
DEFAULT_PERIOD = "30d"
