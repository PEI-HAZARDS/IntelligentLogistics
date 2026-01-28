#!/bin/bash
# ============================================================================
# Setup SSH Keys - Distribui chaves SSH do Jenkins para todas as VMs
# 
# Uso: docker exec -it jenkins setup-ssh-keys.sh
#
# Este script:
# 1. Gera um par de chaves SSH se não existir (persistente em ./ssh_keys/)
# 2. Usa ssh-copy-id para copiar a chave pública para cada VM
# 3. Testa a conexão a cada VM
#
# As chaves são montadas de ./ssh_keys/ e persistem entre rebuilds!
# ============================================================================

set -e

# Definir HOME corretamente para o Jenkins
export HOME="/var/jenkins_home"
SSH_DIR="$HOME/.ssh"
KEY_FILE="$SSH_DIR/id_ed25519"
SSH_USER="pei_user"

# Lista de VMs
declare -A VMS=(
    ["Agent A"]="10.255.32.134"
    ["Agent B"]="10.255.32.32"
    ["Agent C"]="10.255.32.128"
    ["Streaming"]="10.255.32.80"
    ["Kafka"]="10.255.32.143"
    ["Data Module"]="10.255.32.82"
    ["Decision Engine"]="10.255.32.104"
    ["API Gateway"]="10.255.32.100"
    ["UI"]="10.255.32.108"
)

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║          🔐 Setup SSH Keys - IntelligentLogistics             ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Criar diretório SSH se não existir
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"

# Gerar chaves se não existirem
if [[ ! -f "$KEY_FILE" ]]; then
    echo "🔑 Gerando par de chaves SSH..."
    ssh-keygen -t ed25519 -f "$KEY_FILE" -N "" -C "jenkins@intelligentlogistics"
    echo "✅ Chaves geradas em $KEY_FILE"
else
    echo "✅ Chaves já existem em $KEY_FILE"
fi

# Configurar SSH config se não existir
if [[ ! -f "$SSH_DIR/config" ]]; then
    cat > "$SSH_DIR/config" << EOF
Host *
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
    IdentityFile $KEY_FILE
EOF
    chmod 600 "$SSH_DIR/config"
    echo "✅ Configuração SSH criada"
fi

echo ""
echo "📋 A distribuir chaves para as VMs..."
echo "   (Pode ser pedida a password para cada VM na primeira vez)"
echo ""

# Contador de sucesso
SUCCESS=0
FAILED=0

for NAME in "${!VMS[@]}"; do
    IP="${VMS[$NAME]}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🖥️  $NAME ($IP)"
    
    # Verificar se a VM está acessível
    if ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/$IP/22" 2>/dev/null; then
        echo "   ❌ VM não acessível (porta 22 fechada ou offline)"
        ((FAILED++))
        continue
    fi
    
    # Tentar conexão sem password primeiro (chave já copiada?)
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_USER@$IP" "echo 'ok'" 2>/dev/null; then
        echo "   ✅ Chave já configurada"
        ((SUCCESS++))
        continue
    fi
    
    # Copiar chave com ssh-copy-id (sem suprimir output para ver prompt de password)
    echo "   🔄 A copiar chave pública..."
    if ssh-copy-id -i "$KEY_FILE.pub" "$SSH_USER@$IP"; then
        echo "   ✅ Chave copiada com sucesso"
        ((SUCCESS++))
    else
        echo "   ❌ Falha ao copiar chave (verifica password ou permissões)"
        ((FAILED++))
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║              ✅ SETUP COMPLETO - $SUCCESS VMs configuradas              ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
else
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║  ⚠️  SETUP PARCIAL - $SUCCESS OK, $FAILED falharam                       ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
fi

echo ""
echo "🧪 Testar conexão:"
echo "   docker exec jenkins ssh $SSH_USER@10.255.32.134 'docker ps'"
echo ""
