#!/bin/bash
# EC2 首次设置脚本
# 在 EC2 实例上运行此脚本以完成初始配置
# 支持 Ubuntu 和 Amazon Linux 2023

set -e

echo "=== LightRAG Web EC2 初始设置 ==="

# 检测操作系统类型
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "无法检测操作系统类型"
    exit 1
fi

echo "检测到操作系统: $OS"

# 检查是否为 root 用户
if [ "$EUID" -eq 0 ]; then 
   echo "请不要使用 root 用户运行此脚本"
   exit 1
fi

# 根据操作系统选择包管理器
if [[ "$OS" == "ubuntu" ]]; then
    # Ubuntu/Debian 系统
    echo "更新系统..."
    sudo apt update && sudo apt upgrade -y
    
    echo "安装 Python..."
    sudo apt install -y python3 python3-pip python3-venv
    
    echo "安装 Node.js..."
    # ⚠️ 注意: 前端构建在 GitHub Actions 中完成，EC2 只需提供静态文件
    # 如果只需要运行应用，可以不安装 Node.js
    # 如果需要开发或调试，可以安装 Node.js
    if ! command -v node &> /dev/null; then
        echo "跳过 Node.js 安装（前端构建在 CI/CD 中完成）"
        echo "如需安装，可取消注释以下命令："
        echo "# curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -"
        echo "# sudo apt install -y nodejs"
    else
        echo "Node.js 已安装: $(node --version)"
    fi
    
    echo "安装 Nginx..."
    if ! command -v nginx &> /dev/null; then
        sudo apt install -y nginx
    else
        echo "Nginx 已安装"
    fi
    
    echo "安装 Git..."
    sudo apt install -y git
    
    echo "配置防火墙..."
    sudo ufw allow 22/tcp   # SSH
    sudo ufw allow 80/tcp   # HTTP
    sudo ufw allow 443/tcp  # HTTPS
    sudo ufw --force enable
    
elif [[ "$OS" == "amzn" ]] || [[ "$OS" == "fedora" ]]; then
    # Amazon Linux 2023 或 Fedora 系统
    echo "更新系统..."
    sudo yum update -y
    
    echo "安装 Python..."
    sudo yum install -y python3 python3-pip git
    
    # 创建 python3-venv（Amazon Linux 2023 可能不包含）
    python3 -m pip install --upgrade pip
    
    echo "安装 Node.js..."
    # ⚠️ 注意: 前端构建在 GitHub Actions 中完成，EC2 只需提供静态文件
    # 如果只需要运行应用，可以不安装 Node.js
    # 如果需要开发或调试，可以安装 Node.js
    if ! command -v node &> /dev/null; then
        echo "跳过 Node.js 安装（前端构建在 CI/CD 中完成）"
        echo "如需安装，可取消注释以下命令："
        echo "# curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -"
        echo "# sudo yum install -y nodejs"
    else
        echo "Node.js 已安装: $(node --version)"
    fi
    
    echo "安装 Nginx..."
    if ! command -v nginx &> /dev/null; then
        sudo yum install -y nginx
    else
        echo "Nginx 已安装"
    fi
    
    echo "配置防火墙..."
    # Amazon Linux 2023 使用 firewalld，但通常通过 Security Groups 管理
    # 如果需要，可以启用 firewalld
    if command -v firewall-cmd &> /dev/null; then
        sudo systemctl start firewalld 2>/dev/null || true
        sudo systemctl enable firewalld 2>/dev/null || true
        sudo firewall-cmd --permanent --add-service=ssh 2>/dev/null || true
        sudo firewall-cmd --permanent --add-service=http 2>/dev/null || true
        sudo firewall-cmd --permanent --add-service=https 2>/dev/null || true
        sudo firewall-cmd --reload 2>/dev/null || true
    else
        echo "注意: 防火墙通过 AWS Security Groups 管理，无需额外配置"
    fi
else
    echo "不支持的操作系统: $OS"
    exit 1
fi

# 创建应用目录
echo "创建应用目录..."
sudo mkdir -p /opt/lightrag-web
sudo chown $USER:$USER /opt/lightrag-web

# 创建必要的子目录
mkdir -p /opt/lightrag-web/backend/uploads
mkdir -p /opt/lightrag-web/backend/data
mkdir -p /opt/lightrag-web/backend/uploads/conversations
mkdir -p /opt/lightrag-web/backend/uploads/metadata
mkdir -p /opt/lightrag-web/backend/uploads/image_cache

# 设置目录权限
chmod -R 755 /opt/lightrag-web

echo ""
echo "=== 初始设置完成 ==="
echo ""
echo "下一步："
echo "1. 配置 GitHub Secrets (EC2_INSTANCE_IP, EC2_SSH_KEY)"
echo "2. 触发 GitHub Actions 部署"
echo "3. 部署完成后，编辑 /opt/lightrag-web/backend/.env 文件"
echo "4. 配置 systemd 服务和 Nginx（见部署指南）"
echo ""


