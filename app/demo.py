"""Gera uma equipe de demonstração com histórico realista (útil para testar o dashboard e o RNF09).

Uso:
    python -m app.demo                      # cria dados se o banco estiver vazio
    python -m app.demo --tasks 250          # tarefas por membro (4 membros ⇒ ~1.000 tarefas)

Os eventos são gravados com datas retroativas pela própria camada de comandos (event sourcing),
então linha do tempo, métricas e previsões refletem o histórico simulado.
Recomenda-se usar um DATA_DIR separado, por exemplo:  DATA_DIR=./data-demo python -m app.demo
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, time, timedelta

from .config import get_settings
from .domain.constants import PHASES, POSTPONE_REASONS
from .domain.timeutil import get_tz, utcnow
from .services import commands
from .services.context import Ctx
from .store import repo
from .store.db import connect, init_db, write_transaction

MEMBERS = [("Ana Souza", "gestor"), ("Pedro Lima", "membro"), ("Carla Mendes", "membro"), ("Rafael Costa", "membro"), ("Júlia Rocha", "membro")]
REQUESTERS = ["Carlos", "Marina", "Diretoria", "Cliente Aurora", "Juliana", "Time de Dados", "Financeiro", "RH"]
TOPICS = [
    ("Relatório mensal de vendas", "Consolidar números do mês e comentar variações."),
    ("Apresentação para a diretoria", "Slides com resultados e próximos passos."),
    ("Revisar contrato de fornecedor", "Checar cláusulas de SLA e multas."),
    ("Atualizar planilha de horas", "Lançar horas da semana por projeto."),
    ("Migrar dashboard para a nova base", "Trocar conexões e validar indicadores."),
    ("Treinamento de segurança", "Módulo obrigatório de segurança da informação."),
    ("Planejar sprint", "Priorizar backlog e estimar esforço."),
    ("Corrigir bug de exportação", "Arquivo CSV sai com acentuação errada."),
    ("Documentar API de pedidos", "Endpoints, exemplos e códigos de erro."),
    ("Pesquisa com clientes", "Roteiro, recrutamento e síntese."),
    ("Estudar capítulo de cálculo", "Limites e derivadas — lista 3."),
    ("Organizar evento de integração", "Local, orçamento e convites."),
    ("Revisar proposta comercial", "Ajustar escopo e cronograma."),
    ("Configurar ambiente de testes", "Banco, dados de exemplo e pipeline."),
    ("Análise de churn do trimestre", "Segmentar clientes e causas."),
]
STEPS = [
    ["Levantar dados", "Montar primeira versão", "Revisar com o time", "Enviar"],
    ["Definir escopo", "Rascunhar", "Validar com solicitante"],
    ["Ler material", "Anotar dúvidas", "Resolver exercícios", "Revisar erros"],
    ["Mapear requisitos", "Implementar", "Testar", "Publicar", "Comunicar"],
    [],
]
GOALS = [
    ("Passar em Cálculo", 50),
    ("Lançar o novo dashboard", 35),
    ("Reduzir atrasos no trimestre", 70),
    ("Certificação em segurança", 20),
]


def _at(rng: random.Random, day: datetime, tz) -> datetime:
    local = datetime.combine(day.date(), time(rng.randint(8, 18), rng.randint(0, 59)), tz)
    return local.astimezone(utcnow().tzinfo)


def seed(tasks_per_member: int = 200, seed_value: int = 42) -> dict:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    rng = random.Random(seed_value)
    tz = get_tz(settings.timezone)
    now = utcnow()
    try:
        if repo.list_accounts(conn):
            raise SystemExit("O banco já tem contas. Use um DATA_DIR vazio para a demonstração.")
        start = now - timedelta(days=200)

        def ctx(actor, when) -> Ctx:
            return Ctx(conn=conn, actor=actor, occurred_at=min(when, now), tz=tz)

        accounts = []
        with write_transaction(conn):
            for name, role in MEMBERS:
                account = commands.create_account(ctx(None, start), name)
                if role == "gestor":
                    account = commands.change_role(ctx(account, start), account.id, "gestor")
                accounts.append(account)
        manager = accounts[0]

        total = 0
        for account in accounts[1:]:
            with write_transaction(conn):
                goals = []
                for title, days_ahead in rng.sample(GOALS, 2):
                    goal = commands.create_goal(
                        ctx(account, start + timedelta(days=rng.randint(0, 30))),
                        account.id,
                        {"title": title, "target_date": (now + timedelta(days=days_ahead - 40)).date().isoformat()},
                    )
                    goals.append(goal)
                for i in range(tasks_per_member):
                    total += 1
                    age = rng.triangular(0, 200, 0)  # mais tarefas recentes
                    stuck = rng.random() < 0.08  # parte do backlog nunca anda (gera atrasadas e paradas)
                    created = _at(rng, now - timedelta(days=age), tz)
                    title, description = rng.choice(TOPICS)
                    difficulty = rng.choices(["facil", "medio", "dificil"], [0.35, 0.45, 0.2])[0]
                    effort = {"facil": 2, "medio": 5, "dificil": 9}[difficulty]
                    priority = rng.choices(["baixa", "media", "alta", "muito_alta"], [0.25, 0.4, 0.25, 0.1])[0]
                    due = created + timedelta(days=rng.randint(1, effort * 2 + 3)) if rng.random() < 0.85 else None
                    steps = rng.choice(STEPS)
                    goal = rng.choice(goals) if rng.random() < 0.3 else None
                    task = commands.create_task(
                        ctx(account, created),
                        account.id,
                        {
                            "title": f"{title} #{i + 1}",
                            "description": description,
                            "difficulty": difficulty,
                            "priority": priority,
                            "due_date": due.date().isoformat() if due else None,
                            "requester": rng.choice(REQUESTERS) if rng.random() < 0.8 else "",
                            "goal_id": goal.id if goal else None,
                            "steps": steps,
                        },
                    )
                    duration = timedelta(days=rng.gammavariate(2.0, effort / 2.0))
                    finish = created + duration
                    # adiamentos com motivo (RN21) antes da conclusão
                    if due and rng.random() < 0.22:
                        when = created + (min(finish, now) - created) * rng.uniform(0.3, 0.9)
                        new_due = due + timedelta(days=rng.randint(2, 10))
                        reason = rng.choices(list(POSTPONE_REASONS), [0.4, 0.3, 0.2, 0.1])[0]
                        commands.update_task(
                            ctx(account, when),
                            task.id,
                            {"due_date": new_due.date().isoformat(), "due_reason": reason, "due_reason_text": "Aguardando retorno do cliente" if reason == "outro" else ""},
                        )
                    # fase evolui com o tempo
                    phase_index = min(len(PHASES) - 1, int((min(finish, now) - created) / max(duration, timedelta(hours=1)) * rng.randint(2, 5)))
                    if phase_index:
                        commands.update_task(ctx(account, created + (min(finish, now) - created) * 0.5), task.id, {"phase": PHASES[phase_index]})
                    # etapas marcadas ao longo da execução
                    current = repo.get_task(conn, task.id)
                    done_until = min(finish, now)
                    if stuck:
                        done_until = created + (done_until - created) * rng.uniform(0.0, 0.6)
                    for index, step in enumerate(current.steps):
                        moment = created + (finish - created) * ((index + 1) / (len(current.steps) + 0.2))
                        if moment <= done_until:
                            commands.update_step(ctx(account, moment), task.id, step.id, {"done": True})
                    if finish <= now and not current.steps and not stuck:
                        commands.set_task_done(ctx(account, finish), task.id, True)
                # templates
                commands.create_template(ctx(account, start), account.id, {"name": "Relatório padrão", "title": "Relatório mensal", "difficulty": "medio", "steps": STEPS[0]})
                pending = [t for t in repo.list_tasks(conn, account.id) if t.is_pending]
                commands.set_top3(ctx(account, now), account.id, [t.id for t in pending[:3]])

        with write_transaction(conn):
            for account in accounts[1:]:
                # atribuições recentes do Gestor (RF64), ainda não vistas (RF65)
                assigned = commands.create_task(
                    ctx(manager, now - timedelta(hours=rng.randint(1, 20))),
                    account.id,
                    {"title": "Revisar indicadores do trimestre", "difficulty": "medio", "due_date": (now + timedelta(days=3)).date().isoformat(), "steps": ["Conferir números", "Comentar variações"]},
                )
                commands.add_comment(ctx(manager, now - timedelta(minutes=30)), assigned.id, "Consegue priorizar esta semana? Obrigado!")
                pending = [t for t in repo.list_tasks(conn, account.id) if t.is_pending and not t.assigned_by]
                if pending:
                    commands.add_comment(ctx(manager, now - timedelta(hours=5)), pending[0].id, "Como está o andamento? Precisa de ajuda?")
        return {"accounts": len(accounts), "tasks": total}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera dados de demonstração.")
    parser.add_argument("--tasks", type=int, default=200, help="tarefas por membro (padrão: 200)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = seed(args.tasks, args.seed)
    print(f"Demonstração criada: {result['accounts']} contas, {result['tasks']} tarefas em {get_settings().db_path}")


if __name__ == "__main__":
    main()
