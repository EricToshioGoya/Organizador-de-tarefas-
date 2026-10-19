"""Gera uma equipe de demonstração com histórico realista (útil para testar o dashboard e o RNF09),
incluindo a agenda de cada conta na aba Calendário, a Daily de ontem, hoje e amanhã e duas listas na aba Listas.

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


MEETINGS = [
    ("Revisão com o cliente", "Teams", "laranja"),
    ("Alinhamento com o time de dados", "Sala 2", "verde"),
    ("Entrevista de candidato", "Sala 4", "roxo"),
    ("Apresentação de resultados", "Auditório", "vermelho"),
    ("Workshop de planejamento", "Sala 3", "amarelo"),
    ("Café com o time", "Copa", "cinza"),
]


def _calendar(ctx, rng: random.Random, account, today, manager_name: str, is_manager: bool) -> None:
    """Agenda da conta: reuniões que se repetem, compromissos das próximas semanas e um evento particular."""
    monday = today - timedelta(days=today.weekday())
    first = monday - timedelta(weeks=8)
    weekly = commands.create_calendar_entry(
        ctx,
        account.id,
        {
            "title": "Reunião semanal da equipe",
            "start_date": first.isoformat(),
            "start_time": "09:30",
            "end_time": "10:30",
            "location": "Sala 3",
            "notes": "Pauta: entregas da semana, bloqueios e prioridades.",
            "recurrence": {"freq": "semanal", "weekdays": [0]},
        },
    )
    commands.exclude_occurrence(ctx, weekly.id, (monday - timedelta(weeks=3)).isoformat())  # feriado
    if not is_manager:
        commands.create_calendar_entry(
            ctx,
            account.id,
            {
                "title": f"1:1 com {manager_name.split()[0]}",
                "start_date": (first + timedelta(days=2)).isoformat(),
                "start_time": "14:00",
                "end_time": "14:30",
                "color": "roxo",
                "recurrence": {"freq": "semanal", "interval": 2},
            },
        )
    for week in range(3):
        for _ in range(rng.randint(2, 4)):
            title, location, color = rng.choice(MEETINGS)
            day = monday + timedelta(weeks=week, days=rng.randint(0, 4))
            start = rng.choice([8, 10, 11, 13, 15, 16]) * 60 + rng.choice([0, 30])
            length = rng.choice([30, 60, 60, 90])
            commands.create_calendar_entry(
                ctx,
                account.id,
                {
                    "title": title,
                    "start_date": day.isoformat(),
                    "start_time": f"{start // 60:02d}:{start % 60:02d}",
                    "end_time": f"{(start + length) // 60:02d}:{(start + length) % 60:02d}",
                    "location": location,
                    "color": color,
                },
            )
    training = monday + timedelta(weeks=1, days=rng.randint(0, 3))
    commands.create_calendar_entry(
        ctx,
        account.id,
        {"title": "Treinamento de segurança", "all_day": True, "start_date": training.isoformat(), "end_date": (training + timedelta(days=1)).isoformat(), "color": "cinza"},
    )
    commands.create_calendar_entry(
        ctx,
        account.id,
        {
            "title": "Consulta médica",
            "start_date": (monday + timedelta(days=rng.randint(0, 4))).isoformat(),
            "start_time": "17:00",
            "end_time": "18:00",
            "private": True,
            "notes": "Levar exames.",
        },
    )


DAILY = [
    "Responder e-mails do cliente",
    "Revisar a planilha de horas",
    "Ligar para o fornecedor",
    "Conferir a agenda do dia",
    "Enviar o relatório para a Marina",
    "Atualizar o quadro da sprint",
    "Separar os documentos da reunião",
    "Organizar a caixa de entrada",
]


def _daily(ctx, rng: random.Random, account, today, now: datetime) -> None:
    """Daily: ontem (com uma pendência que aparece hoje), hoje e amanhã."""
    titles = rng.sample(DAILY, 7)
    plan = [(-1, True), (-1, False), (-1, True), (0, True), (0, False), (0, False), (1, False)]
    for index, ((offset, done), title) in enumerate(zip(plan, titles)):
        when = now + timedelta(days=min(offset, 0), hours=-8 + index)
        item = commands.create_daily_item(
            ctx(account, when),
            account.id,
            {"title": title, "day": (today + timedelta(days=offset)).isoformat(), "note": "Prazo: fim do dia." if index == 4 else ""},
        )
        if done:
            commands.update_daily_item(ctx(account, when + timedelta(hours=1)), item.id, {"done": True})


SHOPPING = [("Café", 500, "g"), ("Arroz", 5, "kg"), ("Leite", 6, "L"), ("Pão de forma", 1, ""), ("Ovos", 12, "un"), ("Detergente", 2, "")]
IDEAS = ["Automatizar o relatório semanal", "Testar o novo layout do painel", "Documentar o processo de deploy"]


def _lists(ctx, account, now: datetime) -> None:
    """Listas: uma lista de compras em ranking (com quantidades) e uma lista de tarefas."""
    when = now - timedelta(days=2)
    shopping = commands.create_user_list(ctx(account, when), account.id, {"name": "Lista de compras", "kind": "ranking"})
    for index, (title, quantity, unit) in enumerate(SHOPPING):
        item = commands.create_list_item(ctx(account, when + timedelta(minutes=index)), shopping.id, {"title": title, "quantity": quantity, "unit": unit})
        if title == "Ovos":
            commands.update_list_item(ctx(account, now - timedelta(hours=3)), item.id, {"done": True})
    ideas = commands.create_user_list(ctx(account, when + timedelta(hours=1)), account.id, {"name": "Ideias", "kind": "tarefas"})
    for index, title in enumerate(IDEAS):
        item = commands.create_list_item(ctx(account, when + timedelta(hours=1, minutes=index)), ideas.id, {"title": title})
        if index == 0:
            commands.update_list_item(ctx(account, now - timedelta(hours=1)), item.id, {"done": True})


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
            # calendário de cada conta (aba Calendário)
            today = now.astimezone(tz).date()
            for account in accounts:
                _calendar(ctx(account, now - timedelta(days=60)), rng, account, today, manager.name, account.id == manager.id)
                _daily(ctx, rng, account, today, now)
                _lists(ctx, account, now)
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
