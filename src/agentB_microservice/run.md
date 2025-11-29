
estar na pasta do agentB

docker build -t agentb:latest

docker run -d agentb:latest


# Para ver nome da imagem
docker ps -a

# Para ver os logs
docker logs -f <nome-imagem>