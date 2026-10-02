# Organizador de Tarefas

Aplicação web para a equipe organizar tarefas em etapas, agrupadas em metas, com fases de
desenvolvimento, dashboard de desempenho e acompanhamento pelo Gestor. Implementa a especificação
**v1.2 (23/09/2026)**: requisitos funcionais RF01–RF71, regras RN01–RN36 e não funcionais RNF01–RNF25.

- **Back end:** Python 3.11+ · FastAPI · SQLite com *event sourcing* (cada alteração é um evento imutável).
- **Front end:** PWA em JavaScript moderno sem etapa de build (Preact + htm), gráficos com Apache ECharts.
- **API REST** documentada em OpenAPI: `/api/docs` (Swagger) e `/api/redoc`.

## Como rodar (Windows)

```powershell
.\run.ps1
```

Abra <http://localhost:8000>. Na primeira vez, o script cria um ambiente virtual em
`%LOCALAPPDATA%\OrganizadorDeTarefas\venv` e instala as dependências. O projeto está no OneDrive, então
ambiente e dados ficam **fora** dele: sincronizar um banco SQLite em uso pode corrompê-lo.

| Comando | O que faz |
|---|---|
| `.\run.ps1` | Inicia em `http://localhost:8000` |
| `.\run.ps1 -Port 8080 -Lan` | Aceita conexões de outros computadores da rede |
| `.\run.ps1 -Demo` | Usa um banco separado com uma equipe de demonstração (~1.000 tarefas) |
| `.\run.ps1 -Test` | Roda os testes com relatório de cobertura |

Se o Windows bloquear scripts: `powershell -ExecutionPolicy Bypass -File .\run.ps1`.
Em servidores Linux/macOS: `./run.sh` (ou `./run.sh test`).

## Uso em equipe

Os dados ficam centralizados no servidor (RNF17). Para a equipe usar:

1. Rode em uma máquina ou VM acessível pela rede (`.\run.ps1 -Lan` ou `./run.sh`).
2. **Publique com HTTPS** (proxy reverso como IIS, nginx ou Caddy, ou `uvicorn --ssl-keyfile/--ssl-certfile`).
   Navegadores só ativam o service worker em HTTPS ou `localhost`, então instalação como app e uso offline
   (RNF20) dependem disso. Sem HTTPS, o app funciona online normalmente.
3. Defina `PUBLIC_URL` no `.env` para os links do resumo diário e do calendário.

> **Sem autenticação, por decisão de projeto (RNF18, RN10, RN11).** Qualquer pessoa com acesso ao endereço
> pode entrar em qualquer conta. Use só na rede interna e com dados não sensíveis.

## Configuração

Copie `.env.example` para `.env` e ajuste o que precisar. Todas as variáveis são opcionais:

| Variável | Uso |
|---|---|
| `DATA_DIR` | Pasta do banco `organizador.sqlite3` e dos anexos |
| `APP_TIMEZONE` | Fuso padrão (o navegador informa o fuso de cada pessoa) |
| `PUBLIC_URL` | Endereço público, usado em links |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Geração de etapas por IA (RF52). Padrão: `claude-opus-5` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | Resumo diário por e-mail (RF56) |
| `TELEGRAM_BOT_TOKEN` | Resumo diário pelo Telegram (RF56) |
| `MAX_UPLOAD_MB` | Limite por anexo (padrão 20) |

**IA (RF52).** Sem chave, o botão de IA fica oculto e o restante funciona. Com chave, o **título e a
descrição da tarefa são enviados à API da Anthropic**; confirme a política da empresa sobre envio de dados a
serviços externos antes de ativar. A chamada é feita só pelo servidor (a chave nunca vai ao navegador), usa
esforço baixo e saída JSON estruturada, tem limite de 10 s (RNF23) e ativa o *fallback* do servidor para
recusas dos classificadores de segurança. As etapas sugeridas só são gravadas depois que a pessoa revisa e
confirma (RN26).

**Resumo diário (RF56).** Cada pessoa ativa em *Configurações da conta* o horário, o e-mail e/ou o ID do chat
do Telegram (RN29). O servidor verifica a cada 30 s e envia no horário de cada conta.

**Calendário (RF55).** Cada conta tem um feed `.ics` (endereço em *Configurações da conta*). O Outlook assina
feeds da rede interna; o Google Agenda só lê endereços públicos na internet.

## Testes (RNF15)

```powershell
.\run.ps1 -Test
```

São 116 testes (pytest) cobrindo regras de negócio, métricas, previsões, integrações e fluxos completos da
API. Cobertura: 95% no total e ~99% nos módulos de regras (`app/domain`) e métricas (`app/metrics`).

## Arquitetura (RNF14, RNF22)

```
app/
  domain/        regras de negócio puras (RN01–RN36), criação rápida (RN19), datas
  metrics/       KPIs, gráficos G1–G12, capacidade (RN25), Monte Carlo (RN28), similaridade (RN27), revisão semanal
  services/      comandos: validam regras, emitem eventos e aplicam regras derivadas; linha do tempo (RF48)
  store/         SQLite: eventos imutáveis + projeções de leitura reconstruíveis
  api/           rotas REST, esquemas OpenAPI, cabeçalhos de contexto e idempotência
  integrations/  IA (Anthropic), calendário .ics, e-mail/Telegram e agendador
  demo.py        gerador de dados de demonstração
web/             PWA: index.html, service worker, CSS (tokens do design system) e módulos JS
tests/           testes automatizados
docs/            design system e validação da paleta
```

- **Event sourcing.** Toda alteração vira um evento (`TarefaCriada`, `EtapaConcluida`, `PrazoAlterado`…),
  protegido por *triggers* contra alteração e exclusão. As tabelas de leitura são projeções e podem ser
  reconstruídas a partir dos eventos (`store.projector.rebuild_projections`). A linha do tempo vem dos eventos.
- **Salvamento automático e offline (RF06, RF69–RF71, RN30, RN35).** O navegador grava cada alteração numa
  fila local antes de enviá-la. Marcações e seleções são enviadas na hora; textos, 1 s depois da última
  digitação. Sem conexão, as alterações ficam no aparelho e são reenviadas com a mesma chave de idempotência.
  Em conflito, prevalece a alteração mais recente, comparada campo a campo pelo horário da ação.
- **Atualização entre contas (RNF19).** O navegador consulta `/api/changes` a cada 10 s.

## Decisões de interpretação

Pontos em que a especificação admite mais de uma leitura. A regra adotada está implementada e testada:

1. **Filtro de período.** Pendentes e atrasadas mostram o estado atual. Concluídas, % no prazo e tempo médio
   consideram as tarefas concluídas no período. G2, G4 e G12 usam "pendentes + concluídas no período".
   G10 e G11 independem do filtro (G11 por regra; G10 porque carga e capacidade têm janelas próprias).
2. **Tarefa com etapas.** O checkbox da tarefa conclui marcando as etapas restantes (com confirmação). Para
   reabrir, desmarca-se uma etapa (RN02–RN04).
3. **Criação rápida.** Se um tipo de marcador aparece mais de uma vez, vale o último; as ocorrências anteriores
   ficam no título. `dd/mm` já passado no ano vai para o próximo ano (próxima ocorrência, como nos dias da semana).
4. **Mudanças de prazo.** Só o adiamento exige motivo (RN21). Definir, antecipar ou remover a data fica no
   histórico sem motivo.
5. **Top 3.** Uma tarefa concluída depois de escolhida continua no Top 3 daquele dia.
6. **Revisão semanal.** "Atrasadas" são as entregas previstas na semana que não foram concluídas até a data. A
   revisão é gerada no primeiro acesso da semana e guardada.
7. **G10.** As semanas passadas mostram pontos concluídos; a semana atual (com atrasadas) e as 4 seguintes
   mostram a carga prevista; a linha tracejada é a capacidade.
8. **Gestor.** Para o perfil Gestor, a aba Equipe vira o Painel da equipe, que é a tela inicial (RN34).
9. **Somente leitura.** Além da interface (RF37), o servidor recusa alterações de outra conta, exceto
   atribuição e comentário do Gestor (RN32). Isso mantém os dados consistentes, mas **não** é controle de acesso (RN11).
10. **Comentários** ficam fora da linha do tempo, que qualquer pessoa pode ver (RN36).
11. **Sanitização (RNF13).** Textos são preservados como digitados (sem caracteres de controle e com limite de
    tamanho) e sempre escapados na exibição. Links aceitam só `http`, `https` e `mailto`. Anexos que não são
    imagem, PDF ou texto são baixados como arquivo, nunca exibidos no navegador.
12. **Templates (RF42, RF43).** Toda tarefa serve de modelo, sem tela separada de templates. *Duplicar tarefa*
    (menu ⋯ da tarefa) abre uma nova tarefa com título, descrição, dificuldade e etapas desmarcadas, sem datas
    (RN20); de outra conta, a opção é *Copiar para minhas tarefas*. Ao digitar o título de uma nova tarefa, o
    formulário sugere reaproveitar as etapas de tarefas parecidas. A API de templates continua disponível, e
    os modelos salvos antes dessa mudança aparecem entre as sugestões.
13. **Prioridade e ordenação (substitui a ordem por entrega do RF14).** Cada tarefa tem prioridade Baixa, Média,
    Alta ou Muito alta (padrão Média, inclusive para as tarefas já existentes). As pendentes são ordenadas só pela
    prioridade (Muito alta primeiro); no empate, a criada antes vem primeiro. A prioridade e a descrição aparecem
    no cartão e podem ser alteradas ali mesmo (menu da prioridade; clique na descrição para editar).

## Dados de demonstração

```powershell
.\run.ps1 -Demo
```

Cria, num banco separado (`%LOCALAPPDATA%\OrganizadorDeTarefas\demo`), cinco contas (Ana Souza é a Gestora)
e 250 tarefas por membro com histórico de seis meses: etapas, adiamentos com motivo, fases, metas,
atribuições e comentários.
