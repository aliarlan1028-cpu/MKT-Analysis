#!/bin/bash
# ============================================
# CryptoEdge Pro — Vultr 一键部署脚本
# 在 Ubuntu 22.04/24.04 上运行
# ============================================
set -e

echo "🚀 CryptoEdge Pro 部署开始..."

# ── 1. 系统依赖 ──
echo "📦 安装系统依赖..."
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv nodejs npm git curl ufw

# 安装 Node.js 20.x (LTS)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

echo "  Python: $(python3 --version)"
echo "  Node: $(node --version)"
echo "  npm: $(npm --version)"

# ── 2. 防火墙 ──
echo "🔒 配置防火墙..."
ufw allow 22    # SSH
ufw allow 8000  # Backend API
ufw allow 3000  # Frontend
ufw --force enable

# ── 3. 克隆代码 ──
echo "📥 克隆代码..."
cd /root
if [ -d "MKT-Analysis" ]; then
    cd MKT-Analysis && git pull
else
    git clone https://github.com/aliarlan1028-cpu/MKT-Analysis.git
    cd MKT-Analysis
fi

# ── 4. 后端配置 ──
echo "⚙️ 配置后端..."
cd /root/MKT-Analysis/backend

# 创建 .env 文件（部署时需要手动填入你的密钥）
if [ ! -f .env ]; then
cat > .env << 'ENVEOF'
GEMINI_API_KEY=__GEMINI_KEY__
CMC_API_KEY=__CMC_KEY__
DATABASE_URL=sqlite:///./data/reports.db
FRONTEND_URL=http://0.0.0.0:3000
OKX_API_KEY=__OKX_KEY__
OKX_API_SECRET=__OKX_SECRET__
OKX_API_PASSPHRASE=__OKX_PASS__
ENVEOF
echo "⚠️  请编辑 /root/MKT-Analysis/backend/.env 填入你的 API 密钥!"
fi

# 创建虚拟环境 + 安装依赖
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 确保 data 目录存在
mkdir -p data

# ── 5. 前端配置 ──
echo "⚙️ 配置前端..."
cd /root/MKT-Analysis/frontend

# 前端环境变量 — 指向本机后端
cat > .env.local << 'ENVEOF'
NEXT_PUBLIC_API_URL=http://0.0.0.0:8000/api
ENVEOF

npm install
npm run build

# ── 6. 创建 systemd 服务（开机自启 + 自动重启） ──
echo "🔧 创建 systemd 服务..."

# 后端服务
cat > /etc/systemd/system/cryptoedge-backend.service << 'EOF'
[Unit]
Description=CryptoEdge Pro Backend (FastAPI)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/MKT-Analysis/backend
ExecStart=/root/MKT-Analysis/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/root/MKT-Analysis/backend/.env

[Install]
WantedBy=multi-user.target
EOF

# 前端服务
cat > /etc/systemd/system/cryptoedge-frontend.service << 'EOF'
[Unit]
Description=CryptoEdge Pro Frontend (Next.js)
After=network.target cryptoedge-backend.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/MKT-Analysis/frontend
ExecStart=/usr/bin/npm start -- -H 0.0.0.0
Restart=always
RestartSec=5
Environment=PORT=3000

[Install]
WantedBy=multi-user.target
EOF

# ── 7. 启动服务 ──
echo "🚀 启动服务..."
systemctl daemon-reload
systemctl enable cryptoedge-backend cryptoedge-frontend
systemctl start cryptoedge-backend
sleep 3
systemctl start cryptoedge-frontend

echo ""
echo "============================================"
echo "✅ CryptoEdge Pro 部署完成!"
echo "============================================"
echo ""
echo "📊 后端 API: http://$(curl -s ifconfig.me):8000"
echo "🌐 前端界面: http://$(curl -s ifconfig.me):3000"
echo ""
echo "📋 管理命令:"
echo "  查看后端状态: systemctl status cryptoedge-backend"
echo "  查看前端状态: systemctl status cryptoedge-frontend"
echo "  查看后端日志: journalctl -u cryptoedge-backend -f"
echo "  重启后端:     systemctl restart cryptoedge-backend"
echo "  重启前端:     systemctl restart cryptoedge-frontend"
echo ""
echo "⚠️  别忘了编辑 /root/MKT-Analysis/backend/.env 填入 API 密钥!"
echo "============================================"

