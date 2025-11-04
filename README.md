# LightRAG Web 应用

基于 LightRAG 的知识图谱构建和智能问答 Web 应用，支持 PPTX/PDF 文档上传、知识抽取、知识图谱可视化展示和智能对话。

## 项目结构

```
NLP_project/
├── backend/          # 后端服务（FastAPI）
│   ├── app/         # 应用核心代码
│   ├── venv/        # Python 虚拟环境（不提交到 Git）
│   └── requirements.txt
├── frontend/         # 前端应用（Vue 3 + Vite）
│   ├── src/         # 源代码
│   ├── node_modules/ # Node 依赖（不提交到 Git）
│   └── package.json
├── LightRAG/        # LightRAG 框架核心代码
└── start_all.bat    # 一键启动脚本
```

## 环境要求

### 后端
- Python 3.10+
- pip
- Windows 10+（PPTX 渲染需要）

### 前端
- Node.js 16+
- npm 或 yarn

## 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd NLP_project
```

### 2. 后端环境配置

```bash
# 进入后端目录
cd backend

# 创建虚拟环境（Windows）
python -m venv venv

# 激活虚拟环境
# Windows CMD:
venv\Scripts\activate.bat
# Windows PowerShell:
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

### 3. 前端环境配置

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install
```

### 4. 配置环境变量（必需）

**重要**：`LLM_BINDING_API_KEY` 是必需的，请配置环境变量。

在 `backend/` 目录下创建 `.env` 文件：

```bash
# Windows CMD
cd backend
copy .env.example .env

# Windows PowerShell
cd backend
Copy-Item .env.example .env
```

然后编辑 `.env` 文件，填入真实的 API Key：

```env
# LLM 配置（必需）
# 请复制此文件为 .env 并填入真实的 API Key
LLM_BINDING=openai
LLM_MODEL=deepseek-ai/DeepSeek-R1-0528-Qwen3-8B
LLM_BINDING_API_KEY=your-api-key-here
LLM_BINDING_HOST=https://api.siliconflow.cn/v1

# Embedding 配置
EMBEDDING_BINDING=siliconcloud
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
EMBEDDING_DIM=1024
EMBEDDING_BINDING_HOST=http://localhost:11434

# 其他配置（可选，有默认值）
MAX_ASYNC=2
TIMEOUT=400
IMAGE_RESOLUTION=150
MAX_FILE_SIZE=52428800
MAX_FILES_PER_CONVERSATION=20

```

**注意**：
- `.env` 文件不会被提交到 Git（已在 `.gitignore` 中）
- 如果未配置 `.env`，应用将无法正常启动（API Key 必需）
- 参考 `backend/.env.example` 查看所有可配置项

## 部署到生产环境

### AWS EC2 部署

**详细部署指南请参考**: [`部署.md`](部署.md)

**快速步骤**:
1. 创建 EC2 实例（t3.small 或更高）
2. 配置 GitHub Secret: `LLM_BINDING_API_KEY`
3. 推送到 `main` 分支触发自动部署
4. 配置 systemd 服务和 Nginx

---

## 启动应用

### 方式一：一键启动（推荐开发使用）

**Windows:**
```bash
# 双击运行或在命令行执行
start_all.bat
```

**PowerShell:**
```powershell
.\start_all.ps1
```

这会自动启动：
- 后端服务：http://localhost:8000
- 前端应用：http://localhost:5173

### 方式二：分别启动

**启动后端:**
```bash
cd backend
start_server.bat
# 或
venv\Scripts\activate.bat
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**启动前端（新开一个终端）:**
```bash
cd frontend
npm run dev
```

## 访问地址

- **前端应用**: http://localhost:5173
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

## 主要功能

- ✅ 文档上传（支持 PPTX、PDF）
- ✅ 知识抽取和知识图谱构建
- ✅ 知识图谱可视化（交互式图谱）
- ✅ 智能对话（基于知识图谱的问答）
- ✅ 文档浏览（PPTX 支持文本高亮，PDF 仅浏览）
- ✅ 对话历史管理
- ✅ 实时进度显示

## 技术栈

### 后端
- FastAPI - Web 框架
- LightRAG - 知识图谱构建和检索
- pdfplumber - PDF 解析
- python-pptx - PPTX 解析
- Pillow - 图片处理

### 前端
- Vue 3 - 前端框架
- Element Plus - UI 组件库
- Pinia - 状态管理
- Vue Router - 路由管理
- Cytoscape.js - 图谱可视化
- Axios - HTTP 客户端

## 常见问题

### 1. 端口被占用

**检查端口:**
```bash
netstat -ano | findstr ":8000"
netstat -ano | findstr ":5173"
```

**解决方法:** 关闭占用端口的程序或修改端口配置

### 2. 依赖安装失败

**后端:**
```bash
# 升级 pip
python -m pip install --upgrade pip

# 重新安装
pip install -r requirements.txt
```

**前端:**
```bash
# 清除缓存
npm cache clean --force

# 重新安装
npm install
```

### 3. PowerShell 执行策略限制

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 开发说明

### 后端开发

后端使用 FastAPI，支持热重载（`--reload` 参数）。

主要目录：
- `app/api/` - API 路由
- `app/services/` - 业务逻辑
- `app/utils/` - 工具函数

### 前端开发

前端使用 Vite，支持热模块替换（HMR）。

主要目录：
- `src/components/` - Vue 组件
- `src/stores/` - Pinia 状态管理
- `src/services/` - API 服务

## 许可证

本项目使用 MIT 许可证。

## 更多信息

- 详细启动说明：查看 `README_启动说明.md`
- API 文档：启动后端后访问 http://localhost:8000/docs
- 需求文档：查看 `需求文档.md`

