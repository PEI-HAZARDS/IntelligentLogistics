FROM jenkins/jenkins:lts

# Instalar Docker CLI
USER root

RUN apt-get update && apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update && apt-get install -y \
    docker-ce-cli \
    docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Copiar script de setup SSH para /usr/local/bin
# As chaves SSH são montadas de ./ssh_keys/ via docker-compose
COPY setup-ssh-keys.sh /usr/local/bin/setup-ssh-keys.sh
RUN chmod +x /usr/local/bin/setup-ssh-keys.sh

# Manter root para ter acesso ao Docker socket
USER root
