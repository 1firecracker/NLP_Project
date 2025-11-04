#!/bin/bash
# 部署验证脚本
# 在 EC2 实例上运行此脚本以验证部署状态

set -e

echo "=== 部署验证 ==="
echo ""

# 检查目录
echo "1. 检查应用目录..."
if [ -d "/opt/lightrag-web" ]; then
    echo "   ✓ 应用目录存在"
else
    echo "   ✗ 应用目录不存在"
    exit 1
fi

# 检查后端
echo ""
echo "2. 检查后端..."
if [ -d "/opt/lightrag-web/backend" ]; then
    echo "   ✓ 后端目录存在"
    if [ -f "/opt/lightrag-web/backend/.env" ]; then
        echo "   ✓ .env 文件存在"
        if grep -q "LLM_BINDING_API_KEY" /opt/lightrag-web/backend/.env; then
            API_KEY=$(grep "LLM_BINDING_API_KEY" /opt/lightrag-web/backend/.env | cut -d'=' -f2)
            if [ -n "$API_KEY" ] && [ "$API_KEY" != "your-api-key-here" ]; then
                echo "   ✓ API Key 已配置"
            else
                echo "   ⚠  API Key 未配置或使用默认值"
            fi
        fi
    else
        echo "   ⚠  .env 文件不存在"
    fi
    
    if [ -d "/opt/lightrag-web/backend/venv" ]; then
        echo "   ✓ Python 虚拟环境存在"
    else
        echo "   ✗ Python 虚拟环境不存在"
    fi
else
    echo "   ✗ 后端目录不存在"
fi

# 检查前端
echo ""
echo "3. 检查前端..."
if [ -d "/opt/lightrag-web/frontend/dist" ]; then
    echo "   ✓ 前端构建文件存在"
    if [ -f "/opt/lightrag-web/frontend/dist/index.html" ]; then
        echo "   ✓ index.html 存在"
    fi
else
    echo "   ✗ 前端构建文件不存在"
fi

# 检查后端服务
echo ""
echo "4. 检查后端服务..."
if systemctl is-active --quiet lightrag-backend; then
    echo "   ✓ 后端服务正在运行"
    echo "   服务状态:"
    systemctl status lightrag-backend --no-pager -l | head -n 5
else
    echo "   ✗ 后端服务未运行"
    echo "   尝试启动服务..."
    sudo systemctl start lightrag-backend || echo "   启动失败"
fi

# 检查 Nginx
echo ""
echo "5. 检查 Nginx..."
if systemctl is-active --quiet nginx; then
    echo "   ✓ Nginx 正在运行"
else
    echo "   ✗ Nginx 未运行"
fi

# 检查端口
echo ""
echo "6. 检查端口..."
if sudo netstat -tlnp | grep -q ":8000"; then
    echo "   ✓ 端口 8000 (后端) 正在监听"
else
    echo "   ✗ 端口 8000 未监听"
fi

if sudo netstat -tlnp | grep -q ":80"; then
    echo "   ✓ 端口 80 (Nginx) 正在监听"
else
    echo "   ✗ 端口 80 未监听"
fi

# 测试 API
echo ""
echo "7. 测试 API..."
EC2_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "localhost")
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health 2>/dev/null | grep -q "200\|404"; then
    echo "   ✓ 后端 API 可访问 (http://localhost:8000)"
else
    echo "   ✗ 后端 API 不可访问"
fi

if curl -s -o /dev/null -w "%{http_code}" http://localhost/api/health 2>/dev/null | grep -q "200\|404"; then
    echo "   ✓ 通过 Nginx 可访问 API (http://localhost/api)"
    echo "   公网访问地址: http://$EC2_IP"
else
    echo "   ✗ 通过 Nginx 无法访问 API"
fi

echo ""
echo "=== 验证完成 ==="
echo ""
echo "如果所有检查都通过，可以在浏览器中访问:"
echo "  http://$EC2_IP"
echo ""


