┌─────────────────┐
│  AI Agents      │
│  (YOLO)         │
└────────┬────────┘
         │ Publica em Kafka
         ▼
    ┌─────────────────────┐
    │  Kafka Topics       │
    │ • lp_results        │
    │ • hz_results        │
    └────────┬────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Decision Engine         │
    │  • Consome Kafka         │
    │  • Faz matching logic    │
    │  • HTTP POST DataModule  │
    └────────┬─────────────────┘
             │ HTTP POST
             ▼
    ┌───────────────────────────────┐
    │  DATA MODULE (Source of Truth)│
    │  • Recebe via HTTP POST       │
    │  • Persiste MongoDB           │
    │  • Atualiza Postgres          │
    │  • Publica Redis pub/sub      │
    └────────┬──────────┬───────────┘
             │          │
             │ Redis    │ HTTP GET/POST
             ▼          ▼
        ┌─────────┐  ┌──────────┐
        │Cache    │  │Serviços  │
        |         |  │internos  │
        └─────────┘  └──────────┘


-----


       AI Cameras
           │
           ▼
        Kafka
           │
           ▼
   ┌──────────────────┐
   │ Decision Engine   │
   └──────┬─────┬─────┘
          │     │
    (hot data)  │  (cold/historical)
          ▼     ▼
        Redis   MongoDB
      (cache)   (events, analytics)
          │        │
          │        └─► Grafana (estatísticas)
          │
          ▼
     WebSocket Api_Gateway
          ▼
       Frontend UI
          
 -----------------------------

Postgres (TOS interno)
 - chegadas programadas
 - cais atribuídos
 - matrículas registadas
 - operador e entidades
 - tabelas referenciais


----

A implementar: (2º semestre)

1. ESTATÍSTICAS E AGREGAÇÕES (crítico para Grafana!)
Falta um serviço para calcular e armazenar:

Contadores por gate, turno, dia/mês/ano
Tempos médios de descarga
Tempos de entrada
Bottlenecks
Taxa de sucesso/falha OCR