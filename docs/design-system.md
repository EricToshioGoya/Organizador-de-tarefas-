# Design system

Tokens centralizados em [`web/css/tokens.css`](../web/css/tokens.css) (RNF06); componentes em
[`web/css/components.css`](../web/css/components.css) e [`web/js/ui/`](../web/js/ui).

## Identidade (RNF04)

- **Tema claro, limpo e calmo, em camadas de tons neutros** para diferenciar ferramentas e blocos:

  | Camada | Tom | Onde |
  |---|---|---|
  | Fundo | cinza quente `#e9e6df` (`--canvas`) | páginas, corpo da gaveta e de modais em blocos |
  | Ferramentas | creme `#f7f2e6` (`--surface-cream`) | faixas de filtros, busca e criação rápida (`.toolbar`), cabeçalho da gaveta, rodapé de ações dos modais, avisos informativos |
  | Blocos | branco `#ffffff` | cartões de tarefa, meta, membro, KPI e gráfico; seções do detalhe da tarefa; grupos de formulário (`.block`) |
  | Detalhes internos | `#f4f1eb` (`--surface-sunken`) e trilho `#ece5d6` (`--surface-track`) | próxima etapa, estatísticas, controles segmentados, aba ativa |

- A cor aparece em pequenas doses fora dos gráficos: selos de dificuldade e fase com um leve tom da própria
  cor e ícones de seção/KPI com a cor do significado (atrasadas em vermelho, vence hoje em âmbar, concluídas
  em verde, Top 3 em amarelo).
- **Ação principal em grafite** (`--accent: #1d1d1b`), com texto branco. Não há gradientes nem brilhos.
- **Botões maiores e arredondados** (pílula, 44 px de altura; 38 px no tamanho pequeno) que **crescem ao
  passar o mouse** (`--grow: 1.05`; cartões clicáveis e chips usam `--grow-sm`/`--grow`). O efeito vale só
  em dispositivos com mouse (`@media (hover: hover)`) e some com `prefers-reduced-motion`.
- Tipografia: sans-serif do sistema (Segoe UI Variable, SF Pro, Roboto). Números usam **algarismos
  tabulares** (`font-variant-numeric: tabular-nums`) na mesma fonte, alinhados em colunas.
- Movimento de 150–300 ms (`--dur-*`), animação na marcação de etapa e skeleton loading; tudo desligado com
  `prefers-reduced-motion` (RNF07, RNF08).

## Cores de significado

| Papel | Cores | Observação |
|---|---|---|
| Dificuldade (semáforo) | `#16a34a` Fácil · `#eab308` Médio · `#dc2626` Difícil | sempre com o rótulo ao lado |
| Fase (escala) | `#fde047` Planejamento → `#f59e0b` Em produção → `#ea580c` Alpha → `#a91b25` Beta | do amarelo claro ao vermelho intenso |
| Fase concluída | `#16a34a` Concluído | a única fase em verde |
| Status (reservado) | bom `#16a34a` · atenção `#d97706` · sério `#ea580c` · crítico `#dc2626` | sempre com ícone + texto |

Os pontos coloridos têm um contorno sutil (`--dot-ring`) para que o amarelo claro continue visível sobre o
branco. Selos de status usam fundo suave com texto escuro da mesma família: 5,8 a 6,3:1 (WCAG AA).

## Cores de dados (RNF05)

Validadas com o método de dataviz (faixa de luminosidade, piso de croma, separação para daltonismo
protan/deutan pelo modelo de Machado et al. 2009, piso de visão normal e contraste) contra a superfície
branca dos gráficos (`--chart-surface: #ffffff`):

| Papel | Cores | Resultado |
|---|---|---|
| Séries categóricas (ordem fixa) | `#2a78d6` azul · `#eb6834` laranja | CVD ΔE 24,7 · normal ΔE 33,6 · contraste ≥ 3:1 |
| Destaque (medidor G3 e metas G8) | gradiente `#2a78d6` → `#1baf7a` | decorativo; o valor está no rótulo |
| Dificuldade (G2, G6) | `#16a34a` · `#eab308` · `#dc2626` | CVD ΔE 11,3 · normal ΔE 24,2; amarelo abaixo de 3:1 → rótulos e tabela |
| Fase (G12 e painel do Gestor) | `#fde047` → `#f59e0b` → `#ea580c` → `#a91b25` · `#16a34a` | luminosidade monotônica, normal ΔE ≥ 15,5; contorno sutil nas barras |
| Heatmap (sequencial) | `#cde2fb` → `#184f95` (6 passos, azul) | monotônica, uma matiz |
| G4 (estado das tarefas) | `#16a34a` concluídas · `#8a8a83` pendentes · `#dc2626` atrasadas | cores de status, contraste ≥ 3:1 |

A escala de fases é pedida pelo significado (amarelo → vermelho) e por isso não é de uma matiz só, e o
amarelo claro de Planejamento fica abaixo de 2:1 sobre o branco. Como compensação, as barras levam rótulo
de valor, contorno sutil e a tabela equivalente.

Texto: `#1d1d1b`, `#4f4f49` e `#62625b` — sobre o branco 16,9 · 8,2 · 6,1:1 e sobre o fundo cinza
13,4 · 6,6 · 4,9:1, todos WCAG AA (RNF12).

Regras aplicadas nos gráficos:

- Uma série → uma cor (slot 1); séries múltiplas usam a ordem fixa, com legenda clicável (RF20).
- Categorias com significado (dificuldade, fase, estado) usam as cores de significado, não cores arbitrárias.
- Linhas de 2 px, barras de até 24 px com cantos de 4 px, grade em linha fina sólida, área em gradiente
  suave; sem brilhos. Rótulos que colidiriam são omitidos (G11) e continuam nos selos e na tabela.
- Cada gráfico tem uma **tabela equivalente** (botão de tabela no cartão) e textos de tooltip escapados.
- Cor nunca é o único indicador: selos de dificuldade, fase e status sempre trazem texto (RNF12).
