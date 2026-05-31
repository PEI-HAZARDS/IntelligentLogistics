# Dinâmicas de análise de dados — Gestor Logístico

> Estado em 2026-05-29. Âmbito: gráficos do gestor logístico orientados a
> **sustentabilidade**, **pontos críticos de logística portuária** e **segurança**.
> Cada dinâmica é classificada por (a) viabilidade com os dados que o backend já
> expõe e (b) justificação quando ficou por fazer.

## Princípio de ancoragem

O frontend consome **apenas** o que o API Gateway (`:8000/api`) expõe. Os endpoints de
estatística atualmente disponíveis e os campos aproveitáveis são:

| Endpoint | Campos |
|---|---|
| `/statistics/summary` | `trucksInPort`, `portCapacity`, `congestionRate`, `peakHour`, `avgWaitingMinutes`, `avgPermanenceMinutes`, `delayRate`, `slaCompliance`, `vehiclesPerHour`, `infractionCount` |
| `/statistics/volume` | série `{timestamp, entries, exits}` por `hour`/`day`/`week` |
| `/statistics/by-company` | `avgWaitingTime`, `avgUnloadingTime`, `slaAttendedRate`, `operationsCount` por transportadora |
| `/statistics/alerts` | breakdown por `type` (safety/problem/operational/generic) com `%` |
| `/statistics/decision-analytics` | `accepted`/`rejected`/`manualReview`, `acceptanceRate`, `avgPipelineMs` |
| `/statistics/sustainability/summary` | `total_co2_kg_estimate`, `avg_co2_per_truck_kg`, `total_waiting_minutes`, `trucks_delayed`, `wait_distribution` (0-5/5-15/15-30/>30 min) |
| `/statistics/sustainability/trend` | série `{period, total_co2_kg, avg_waiting_minutes, trucks_processed}` |

Metodologia de CO₂: **ICCT HDV Roadmap 2023 + EU JRC**, 0,84 kg CO₂/h em ralenti
(camião Euro VI). Tempo de espera = `MAX(0, entry_time − scheduled_start_time)`.

---

## ✅ Implementadas nesta iteração

Todas assentam 100% em dados já existentes — não exigem alterações ao Data Module.

### 1. Histograma de espera → CO₂ evitável (`SustainabilityPage`)
- **O quê:** ao histograma `wait_distribution` (já existente) foi acrescentada a leitura
  de **CO₂ evitável** — minutos de ralenti além de uma janela de tolerância de 5 min,
  estimados pelos pontos médios dos baldes, convertidos a kg CO₂ e a um equivalente
  tangível (km de carro ligeiro, 0,12 kg/km — EEA).
- **Porquê (caso real):** traduz congestão→emissões e dá ao gestor a métrica acionável
  ("quanto CO₂ desaparece se eliminarmos as esperas > tolerância"), o argumento típico
  para investir num *Truck Appointment System*.
- **Limite assumido:** é uma **estimativa** — o cliente só tem contagens por balde, não
  os minutos exatos por camião; rotulada como tal. O backend tem `total_waiting_minutes`
  exato e poderia devolver um corte exato de CO₂ por balde (ver §B abaixo).

### 2. Heatmap de congestão dia-da-semana × hora (`AnalyticsPage`)
- **O quê:** matriz 7×24 (segunda-first) de movimentos totais (`entries + exits`) a partir
  de `/statistics/volume?interval=hour` dos últimos 7 dias; escala de cor verde→âmbar→vermelho.
- **Porquê (caso real):** identifica os **picos recorrentes** que os portos usam para
  desenhar janelas de *appointment* e fazer *peak shaving*. Cruza com `peakHour` do summary.

### 3. Ocupação estimada vs. capacidade (`AnalyticsPage`)
- **O quê:** curva de ocupação no porto ao longo da semana com linhas de referência a
  100% e 80% de `portCapacity`. Como a série só carrega fluxo (entradas/saídas), a curva
  é **ancorada ao valor absoluto conhecido** (`summary.trucksInPort`) e o fluxo horário é
  percorrido para trás a partir dessa âncora.
- **Porquê (caso real):** mostra quando o pátio se aproximou da saturação — ponto crítico
  de segurança e de fila à porta.
- **Limite assumido:** estimativa ancorada no presente; é exata na extremidade (agora) e
  aproximada no passado. Uma série de ocupação absoluta histórica exigiria *snapshots*
  periódicos no backend (ver §A).

---

## ⏸️ Documentadas e adiadas (com justificação)

### A. Ocupação histórica absoluta (em vez de estimada)
- **Falta:** o backend não persiste *snapshots* periódicos de `trucksInPort`; só há o valor
  instantâneo. A curva histórica de ocupação é, por isso, reconstruída por fluxo (estimativa).
- **Para fechar:** projeção CQRS de ocupação por hora (read model em Mongo, alimentado pelo
  outbox worker). Aditivo, compatível com as guardrails. Não foi feito por estar fora do
  âmbito do *sprint* e por a estimativa ancorada ser suficiente para a leitura operacional.

### B. CO₂ evitável **exato** por balde
- **Falta:** `/sustainability/summary` devolve `total_co2_kg_estimate` e `total_waiting_minutes`
  agregados, mas não o CO₂ desagregado por balde de espera nem o corte "além da tolerância".
- **Para fechar:** acrescentar ao endpoint um campo `avoidable_co2_kg` (cálculo já trivial no
  servidor, onde existem os minutos exatos por *appointment*). Aditivo. Mantivemos a estimativa
  no cliente para não tocar no contrato nesta iteração.

### C. Donut de segurança por **classe de mercadoria perigosa (ADR/IMDG)**
- **Falta:** **dados de cargas reais.** O `AgentC` lê placas de perigo (hazmat) na visão
  computacional, mas essa classificação **não está modelada de forma estruturada** nos
  endpoints de estatística — `/statistics/alerts` só dá tipos genéricos
  (safety/problem/operational/generic).
- **Para fechar:** modelar `hazmat_class`/`un_number` no domínio e expor um
  `/statistics/hazmat-breakdown`. Depende de termos um *dataset* de cargas reais classificadas,
  que o projeto não tem (os dados do Porto de Aveiro são de movimento de pesados, sem detalhe
  ADR por veículo). **Bloqueado por falta de dados de cargas reais.**

### D. Heatmap **espacial** do pátio / mapa de calor geográfico
- **Falta:** **routing interno e layout do pátio ficaram por fazer.** Não há coordenadas de
  cais/zonas nem atribuição de posição por veículo no domínio — só estados
  (`in_port`/`unloading`/`done`).
- **Para fechar:** introduzir entidades de *yard layout* (zonas, cais, lugares) e um motor de
  *routing* interno; só então faz sentido um mapa de calor espacial. Fora do âmbito atual.

### E. Cross-filtering / drill-down entre widgets
- **Falta:** clicar numa transportadora (Pareto) ou numa célula do heatmap para filtrar o
  resto do dashboard. Tecnicamente viável com os dados atuais (estado partilhado no cliente),
  mas é uma camada de interação transversal não trivial.
- **Para fechar:** estado de filtro partilhado (contexto React) + re-query com `from/to`/`company`.
  Adiado por custo/benefício face às três visualizações de maior impacto.

### F. Linha-meta na tendência de CO₂
- **Falta:** sobrepor uma linha-alvo (ex.: −10% vs. período anterior) à tendência mensal de
  CO₂ (`Co2TrendChart`) e sombrear a área acima da meta.
- **Para fechar:** cálculo 100% no cliente sobre `/sustainability/trend`; *quick win* deixado
  para uma iteração de polimento, não bloqueado por dados.

### G. Funil de decisão automática (visão computacional)
- **Falta:** funil `accepted → manualReview → rejected` com `avgPipelineMs`, a partir de
  `/statistics/decision-analytics` (dados já existem).
- **Para fechar:** widget de funil; adiado por ser mais métrica de *confiança do sistema* do
  que de sustentabilidade/segurança operacional — prioridade menor neste âmbito.

### H. Análise preditiva (ETA de fila, previsão de pico)
- **Falta:** previsão de congestão/ETA de espera. Exigiria histórico mais longo e um modelo
  (ou dados AIS de chegada de navios para correlacionar procura terrestre↔marítima).
- **Para fechar:** fora de âmbito; depende de dados de séries longas e de integração AIS que
  o projeto não possui. **Bloqueado por falta de dados.**

---

## Resumo

| Dinâmica | Estado | Bloqueio |
|---|---|---|
| 1. Histograma → CO₂ evitável | ✅ Feito | — |
| 2. Heatmap dia×hora | ✅ Feito | — |
| 3. Ocupação vs. capacidade | ✅ Feito | — |
| A. Ocupação histórica absoluta | ⏸️ | Falta snapshot CQRS (aditivo) |
| B. CO₂ evitável exato | ⏸️ | Campo aditivo no endpoint |
| C. Donut hazmat (ADR/IMDG) | ⏸️ | **Dados de cargas reais** |
| D. Heatmap espacial do pátio | ⏸️ | **Routing interno / yard layout por fazer** |
| E. Cross-filtering | ⏸️ | Custo de interação |
| F. Linha-meta CO₂ | ⏸️ | *Quick win* (sem bloqueio de dados) |
| G. Funil de decisão | ⏸️ | Prioridade no âmbito |
| H. Preditivo / AIS | ⏸️ | **Falta de dados (histórico/AIS)** |
