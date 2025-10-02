## Link Colab

https://colab.research.google.com/drive/1lKyl9vISofLvLcQCmpk1yVr6tz7t_ulT?usp=sharing

## Como executar (COLAB)

- 1- Instalar dependencias (ultralytics).
- 2- Dar upload a "dataset.zip" (pelo código)
- 3- Dar upload ao ficheiro "conf.yaml" (manualmente)
- 4- Treinar o modelo.
- 5- Importar resultados para exterior do colab (content/runs/detect/train/wheigh/best.pt).
- 6- Rodar test.py substituindo o ficheiro .pt pelo atual (Pode ser fora do Colab)

## Notas:

- Treinei 2 modelos: 
    - YOLO nano [300 epochs] -> best.pt
    - YOLO large [100 eopchs] -> bestx.pt

- De acordo com o chat, o dataset é pequeno demais para rodar o modelo large com mais que 100/150 iterações (eopchs) sem que ocorra overfitting. 
Eventualmente tem de se fazer data augmentation para diversificar o dataset sem precisar adicionar novas imagens

- Próximo passo: fazer conversão dos json do dataset do Diogo para txt para que sejam compatíveis com YOLO e testar esse dataset
