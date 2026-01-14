#!/bin/bash
# ============================================================================
# Adicionar chave SSH do Jenkins a uma VM
# 
# Uso: ./add-vm.sh <IP_DA_VM> [USER]
#
# Exemplo:
#   ./add-vm.sh 10.255.32.150
#   ./add-vm.sh 10.255.32.150 outro_user
# ============================================================================

set -e

VM_IP="$1"
VM_USER="${2:-pei_user}"

if [ -z "$VM_IP" ]; then
    echo "❌ Uso: $0 <IP_DA_VM> [USER]"
    echo ""
    echo "Exemplos:"
    echo "  $0 10.255.32.150"
    echo "  $0 10.255.32.150 outro_user"
    exit 1
fi

# Diretório do script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUB_KEY_FILE="$SCRIPT_DIR/ssh_keys/id_ed25519.pub"

# Verificar se a chave pública existe
if [ ! -f "$PUB_KEY_FILE" ]; then
    echo "❌ Chave pública não encontrada: $PUB_KEY_FILE"
    echo "   Executa primeiro: docker exec -it jenkins setup-ssh-keys.sh"
    exit 1
fi

PUB_KEY=$(cat "$PUB_KEY_FILE")

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔑 Adicionar chave SSH do Jenkins"
echo "   VM: $VM_USER@$VM_IP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verificar conectividade
echo "🔍 Verificar conectividade..."
if ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/$VM_IP/22" 2>/dev/null; then
    echo "❌ Não foi possível conectar a $VM_IP:22"
    echo "   Verifica se a VM está ligada e acessível"
    exit 1
fi
echo "✅ VM acessível"
echo ""

# Adicionar chave
echo "🔄 A adicionar chave pública..."
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$VM_USER@$VM_IP" \
    "mkdir -p ~/.ssh && chmod 700 ~/.ssh && \
     grep -qF 'jenkins@intelligentlogistics' ~/.ssh/authorized_keys 2>/dev/null || \
     echo '$PUB_KEY' >> ~/.ssh/authorized_keys && \
     chmod 600 ~/.ssh/authorized_keys"

echo "✅ Chave adicionada com sucesso!"
echo ""

# Testar conexão do Jenkins
echo "🧪 A testar conexão do Jenkins..."
if docker exec jenkins ssh -o StrictHostKeyChecking=no -i /var/jenkins_home/.ssh/id_ed25519 "$VM_USER@$VM_IP" "echo OK" 2>/dev/null; then
    echo "✅ Jenkins consegue conectar a $VM_IP"
else
    echo "⚠️  Conexão do Jenkins falhou - verifica se o container está a correr"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ VM $VM_IP configurada!"
echo ""
echo "Para testar manualmente:"
echo "  docker exec jenkins ssh $VM_USER@$VM_IP 'hostname'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
