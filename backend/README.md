# 后端服务

基于 FastAPI 和 LightRAG 的 Web 应用后端。

## 环境要求

- Python 3.9+
- pip

## 安装步骤

1. 创建虚拟环境：
```bash
python -m venv venv
```

2. 激活虚拟环境：
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 配置环境变量：
```bash
# 复制示例文件
copy .env.example .env

# 编辑 .env 文件，填入你的配置
```

5. 启动服务：
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 测试

访问以下 URL 测试服务是否正常：

- http://localhost:8000/ - 根路径
- http://localhost:8000/health - 健康检查
- http://localhost:8000/docs - API 文档（自动生成）
