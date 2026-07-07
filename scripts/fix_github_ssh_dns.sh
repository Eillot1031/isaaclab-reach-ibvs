#!/usr/bin/env bash
# Fix GitHub SSH push: DNS + SSH key config helper.
# Run on the machine where git push fails (needs sudo for DNS steps).

set -euo pipefail

SSH_CONFIG="$HOME/.ssh/config"
KEY="$HOME/.ssh/id_ed25519_github"
GITHUB_HOSTS_LINE="140.82.121.3 github.com"

echo "=== 1. SSH config for github.com ==="
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
touch "$SSH_CONFIG"
chmod 600 "$SSH_CONFIG"

if grep -q '^Host github.com' "$SSH_CONFIG" 2>/dev/null; then
    echo "[OK] github.com block already in $SSH_CONFIG"
else
    cat >> "$SSH_CONFIG" <<'EOF'

Host github.com
    HostName 140.82.121.3
    User git
    IdentityFile ~/.ssh/id_ed25519_github
    IdentitiesOnly yes
EOF
    echo "[OK] Appended github.com to $SSH_CONFIG"
fi

if [[ ! -f "$KEY" ]]; then
    echo "[WARN] Missing $KEY — run ssh-keygen first"
else
    echo "[INFO] Public key (add to GitHub → Settings → SSH keys if not done):"
    cat "${KEY}.pub"
fi

echo ""
echo "=== 2. DNS check ==="
if getent hosts github.com >/dev/null 2>&1; then
    echo "[OK] github.com resolves: $(getent hosts github.com | head -1)"
else
    echo "[FAIL] github.com does not resolve"
    echo "[INFO] Trying public DNS on WiFi interface (needs sudo)..."
    IFACE=$(ip -4 route show default 2>/dev/null | awk '{print $5; exit}')
    if [[ -n "${IFACE:-}" ]]; then
        sudo resolvectl dns "$IFACE" 223.5.5.5 8.8.8.8 || true
        sudo resolvectl flush-caches || true
    fi
    if ! getent hosts github.com >/dev/null 2>&1; then
        echo "[INFO] Adding temporary /etc/hosts entry (needs sudo)..."
        if ! grep -q 'github.com' /etc/hosts 2>/dev/null; then
            echo "$GITHUB_HOSTS_LINE" | sudo tee -a /etc/hosts
        fi
    fi
    if getent hosts github.com >/dev/null 2>&1; then
        echo "[OK] github.com now resolves: $(getent hosts github.com | head -1)"
    else
        echo "[FAIL] Still cannot resolve. Check Mihomo/proxy DNS or reboot network."
        exit 1
    fi
fi

echo ""
echo "=== 3. SSH test ==="
ssh -T -o StrictHostKeyChecking=accept-new git@github.com 2>&1 || true

echo ""
echo "=== 4. Git push ==="
cd /home/krz/isaaclab_ws
git remote -v
git push -u origin main
