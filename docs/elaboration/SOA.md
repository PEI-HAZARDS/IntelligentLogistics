# Comparação entre o Nosso Sistema e o Estado da Arte em Automação de Portos

## 1. Tabela de Funcionalidades

| Feature                       | Our System | Outpost | DockerVision | VisionPlatform.ai | Brainy Neurals |
|-------------------------------|------------|---------|--------------|--------------------|----------------|
| Vehicle Detection             | ✅          | ✅       | ✅            | ✅                  | ✅        | 
| License Plate Recognition     | ✅          | ✅       | ⛔            | ✅                  | 🟨        | 
| Hazardous Cargo Detection     | ✅          | ✅       | ✅            | ✅                  | ⛔        | 
| Automated Entry Authorization | ✅          | ✅       | ⛔            | ✅                  | ✅        | 
| Internal Routing Guidance     | ✅          | ⛔       | ⛔            | ⛔                  | ⛔        |
| Statistical Analysis & Metrics| ✅          | ✅       | ⛔            | 🟨                  | 🟨        |
| Energy Efficiency Optimization| ✅          | ⛔       | ⛔            | ⛔                  | ⛔        | 
| Extensibility/Active Learning | ✅          | ⛔       | ⛔            | ⛔                  | ⛔        | 
| Cost Reduction Focus          | ✅          | ✅       | ✅            | 🟨                  | ✅        | 

---

# 2. Comparação Detalhada

## OUTPOST
### Semelhanças
- Deteta veículos, matrículas e sinais relevantes para entrada.
- Automatiza a validação da entrada do camião.
- Utiliza visão computacional e sistemas de monitorização.

### Diferenças
- Não faz encaminhamento interno no porto.
- Foco operacional em reduzir custos imediatos e usar *voice agents*.
- Menos orientado a aprendizagem ativa ou eficiência energética.

### Diferencial do Nosso Sistema
- Integra **rota interna automática**, preenchendo uma lacuna não coberta pela Outpost.

---

## DockerVision
### Semelhanças
- Forte componente de OCR/Visão para contentores e cargas.
- Deteta sinais perigosos (hazmat) em tempo real.
- Reduz erros humanos e tempos de espera.

### Diferenças
- Centrado na leitura documental; não faz orientação no porto.
- Não inclui módulo estatístico detalhado.
- Não aborda aprendizagem ativa nem eficiência energética.

### Diferencial do Nosso Sistema
- Sistema mais completo por incluir decisão logística + orientação física do camião.

---

## VisionPlatform.ai
### Semelhanças
- Deteção de veículos, matrículas e eventos relevantes.
- Fornece monitorização, alarmes e dashboards.
- Integração via API semelhante à vossa arquitetura.

### Diferenças
- Não decide entrada nem orienta veículos.
- Não contempla aprendizagem ativa.
- Não menciona eficiência energética no pipeline.

### Diferencial
- O nosso sistema é mais operacional: identifica, decide e orienta.

---

## Brainy Neurals
### Semelhanças
- IA aplicada a vários processos portuários.
- Routing, deteção e análise operacional com modelos avançados.

### Diferenças
- Muito mais abrangente (drones, guindastes, planeamento global).
- Não foca especificamente na entrada/encaminhamento de camiões.
- Não contempla aprendizagem ativa para símbolos.

### Diferencial
- Especialização do nosso sistema permite maior precisão no ponto crítico do processo logístico.

---

# 3. Conclusão Geral

O nosso sistema distingue-se por três capacidades chave não encontradas de forma integrada em nenhuma solução analisada:

1. **Encaminhamento interno automático** — Nenhum concorrente o faz.  
2. **Aprendizagem ativa** — Garante adaptação futura e robustez.  
3. **Eficiência energética** — Aplicada diretamente ao processamento da IA em contexto portuário, inovador no setor.

---

# 4. Links

- OUTPOST:  https://www.geekwire.com/2025/how-computer-vision-and-ai-is-being-used-to-boost-efficiency-security-at-truck-terminal-gates/
- Docker vision: https://dockervision.com/how-ai-based-gate-automation-can-reduce-port-expenditure/
- visionplatform.ai: https://visionplatform.ai/ai-video-analytics-for-ports-and-container-terminals/
- Brainy Neurals: https://www.brainyneurals.com/how-ai-is-solving-real-problems-in-shipping-port-operations/