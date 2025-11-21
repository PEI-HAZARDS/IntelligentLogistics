# Intelligent Logistics  

[![Figma](https://img.shields.io/badge/Figma-Design-orange?logo=figma)](https://www.figma.com/files/team/1309815608365821624/project/171687163/PEI?fuid=1309815603742744973)
[![Microsite](https://img.shields.io/badge/Microsite-PEI-blue?logo=github)](https://pei-hazards.github.io/Micro-site/)


## Introdução  
Vivemos numa era em que a logística é invisível mas essencial: as nossas encomendas chegam no dia seguinte com apenas um clique, mas por trás desse processo existem milhões de contentores e operações complexas. Só em 2023, estima-se que **858 milhões de contentores** passaram por portos marítimos em todo o mundo, movimentados por navios, camiões e infraestruturas terrestres.  

Esse volume crescente traz consigo enormes desafios logísticos: atrasos, erros de encaminhamento e custos operacionais. Nos grandes portos — verdadeiros labirintos com dezenas de armazéns — basta uma instrução mal dada para que uma carga seja encaminhada ao destino errado, gerando **perdas de tempo e dinheiro**.  

---

## Motivação  
Para aumentar a **eficiência** e reduzir custos, autoridades portuárias estão a adotar **Tecnologias de Informação e Comunicação (TIC)** e conceitos da **Indústria 4.0**. Com a democratização da **Inteligência Artificial**, da **computação em nuvem** e da **digitalização de processos**, surgem soluções inovadoras para tornar a logística mais **inteligente, automatizada e sustentável**.  

O projeto **Intelligent Logistics** propõe exatamente isso:  
- Automatizar o **controlo de entrada de camiões** num porto.  
- Detetar veículos e cargas através de câmeras e algoritmos de visão computacional.  
- Integrar a informação com um **sistema logístico inteligente** que decide a entrada e destino correto.  
- Informar o condutor de forma clara, seja por **sinalização digital** no porto ou **aplicações móveis**.  

---

## Concepção do Sistema  
O sistema é baseado em dois módulos principais:  

1. **Deteção e Encaminhamento de Cargas**  
   - Utilização de algoritmos de visão computacional em tempo real (ex: YOLO).  
   - Reconhecimento de camiões, matrículas e símbolos de mercadorias perigosas.  
   - Encaminhamento automático para o destino correto dentro do porto.  

2. **Análise Estatística**  
   - Contabilização de veículos, tipos de carga e tempos de permanência.  
   - Visualização de métricas em diferentes granularidades (diário, mensal, individual).  

---

## Requisitos  

### **Funcionais**  
- Deteção automática de camiões em tempo real.  
- Deteção e classificação de matrículas.
- Deteção e classificação de símbolos de mercadorias perigosas.
- Identificação de cargas perigosas através da placa de segurança.
- Gestão de estados de veículos.
- Integração com sistema de gestão logística para tomada de decisão.  
- Encaminhamento do veículo para o destino correto dentro do porto.  
- Notificação clara ao condutor (via sinalização digital ou aplicação móvel).  
- Geração de relatórios estatísticos sobre tráfego e cargas.

### **Não Funcionais**  
- **Eficiência energética**: otimização do uso de recursos computacionais.  
- **Escalabilidade**: permitir adaptação a diferentes portos e cenários.
- **Flexibilidade**: aprendizagem ativa de novos símbolos/tipos de carga (?).  
- **Confiabilidade**: sistema robusto com baixa taxa de erro.
- **Segurança**: proteção dos dados logísticos e dos veículos monitorizados.
- Tempo de resposta: A deteção e notificação não devem exceder 2 segundos entre captura e disponibilização ao operador.
- Confiabilidade: O sistema deve manter uma disponibilidade mínima de 99% no ambiente de produção.

---

## Evoluções Futuras (Fase II)  
- **Aprendizagem ativa**: permitir que o sistema aprenda a identificar novos tipos de carga e símbolos à medida que surgem.  
- **Eficiência energética**: otimizar o uso de recursos de IA em datacenters, equilibrando performance e consumo energético.  

---

## Demonstração  
Existe a possibilidade de integração com **datacenters reais** e redes em funcionamento, bem como a realização de testes práticos em ambiente portuário (como o Porto de Aveiro).  

---

✨ Este projeto combina **IA, visão computacional, logística e eficiência energética**, sendo uma proposta alinhada com os desafios da Indústria 4.0.  


## Future Work

- Interface de administração.
- Interação via dashboard entre o operador da cancela e motorista (?).
- Monitoria
