
estar na pasta do agentA

docker build --rm -t agenta:latest .

docker run -d agenta:

# Para ver nome da imagem
docker ps -a

# Para ver os logs
docker logs -f <nome-imagem>


