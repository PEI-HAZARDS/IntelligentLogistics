
estar na pasta do agentA

docker build \
    --cache-from agenta:latest \
    -t agenta-microservice:latest .

docker run -d agenta:latest

