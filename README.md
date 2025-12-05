# Agent for Exam

基于 LightRAG 的智能考试助手系统，面向教育场景的知识图谱构建、智能问答、试题生成和自动批改的 Web 应用。支持 PPTX/PDF 文档上传、知识抽取、知识图谱可视化、智能对话、AI 生成试题和智能批改功能，并提供基于大模型的智能 Agent 模式，自动编排多种工具完成文档浏览、知识图谱问答和思维导图生成等任务。

![Agent for Exam 系统架构图](./exam%20agent.png)

## Agent 模式简介

本项目内置了基于大模型 Function Calling 的 **智能 Agent 模式**，可以根据用户的自然语言指令自动选择和调用工具，完成与考试场景相关的一系列任务，包括但不限于：

- **文档智能浏览**：自动列出当前对话下的所有教学文档，帮助快速了解可用资料（`list_documents` 工具）。
- **知识图谱问答**：基于 LightRAG 构建的知识图谱，对上传文档进行结构化理解，并支持多模式查询（`query_knowledge_graph` 工具）。
- **思维导图生成**：根据用户指定的文档或问题，自动生成知识结构化的思维导图 / 脑图，支持在前端进行可视化查看（`generate_mindmap` 工具）。

在 Agent 模式下，用户只需要用自然语言表达需求（例如“帮我根据本课 PPT 生成一张思维导图”），系统会自动决定是否调用工具以及调用顺序，并将工具结果整合成最终回答。

## 项目结构

```
NLP_project/
├── backend/                    # 后端服务（FastAPI）
│   ├── app/                    # 应用核心代码
│   │   ├── agents/            # Agent 链式处理模块
│   │   ├── api/               # API 路由
│   │   ├── services/          # 业务逻辑
│   │   └── utils/             # 工具函数
│   ├── venv/                  # Python 虚拟环境（不提交到 Git）
│   └── requirements.txt
├── frontend/                   # 前端应用（Vue 3 + Vite）
│   ├── src/                   # 源代码
│   │   ├── components/       # Vue 组件
│   │   ├── stores/           # Pinia 状态管理
│   │   └── services/         # API 服务
│   └── package.json
├── LightRAG/                   # LightRAG 框架核心代码
└── start_all.ps1              # 一键启动脚本
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

**重要**：以下配置项是必需的，请配置环境变量。

在 `backend/` 目录下创建 `.env` 文件：

```bash
# Windows CMD
cd backend
copy .env.example .env

# Windows PowerShell
cd backend
Copy-Item .env.example .env
```

然后编辑 `.env` 文件，填入 Gitee OCR Token：

```env
# ==================== Gitee OCR 配置（必需）====================
# 默认启用 Gitee OCR 进行 PDF 解析，需要配置 Token
ENABLE_GITEE_OCR=true
GITEE_OCR_TOKEN=your-gitee-ocr-token-here  # 必需：Gitee OCR Token
# 获取方式：https://ai.gitee.com/serverless-api?model=PaddleOCR-VL
每日免费100页解析
```

**必需配置项**：
- **`GITEE_OCR_TOKEN`** - Gitee OCR Token（用于 PDF 解析，默认启用 Gitee OCR）

**获取 Gitee OCR Token**（免费额度：每日100页）：
1. 访问 [Gitee AI 模型广场](https://ai.gitee.com/serverless-api?model=PaddleOCR-VL)
2. 找到 **PaddleOCR-VL** 模型
3. 点击 **"在线体验"**
4. 点击 **"API"** 标签
5. 勾选 **"添加令牌为内嵌代码"**
6. 复制生成的 api_key 到 `.env` 文件中的 `GITEE_OCR_TOKEN`

**注意**：
- `.env` 文件不会被提交到 Git（已在 `.gitignore` 中）
- 如果未配置 `GITEE_OCR_TOKEN`，PDF 解析会失败并回退到本地解析（PyMuPDF/pdfplumber）

### 5. LLM 配置（通过前端界面）

**重要**：LLM API Key 和模型配置通过前端界面进行管理，无需在 `.env` 文件中配置。

启动应用后，点击右上角的 **设置按钮**（⚙️），可以分别配置：

1. **知识图谱抽取**：用于文档知识抽取和知识图谱构建
2. **聊天对话**：用于智能问答和 Agent 模式
3. **思维导图生成**：用于生成思维导图

每个场景可以独立配置：
- **服务商**：目前支持硅基流动（https://siliconflow.cn/）
- **模型**：选择对应的模型（如 DeepSeek-V3.2-Exp、Qwen2.5-VL-7B-Instruct 等）
- **API Key**：输入对应的 API Key（加密存储，不会明文保存）

**配置特点**：
- ✅ **加密存储**：API Key 使用 Fernet 对称加密存储，不会明文保存
- ✅ **立即生效**：配置更新后立即生效，无需重启服务
- ✅ **独立配置**：三个场景的配置完全独立，可以使用不同的模型和 API Key
- ✅ **安全可靠**：配置文件存储在 `backend/data/llm_config.json`，已加入 `.gitignore`，不会被提交到版本控制

**首次使用**：
- 如果未配置 LLM API Key，系统会提示错误
- 请先获取硅基流动的 API Key，然后通过前端设置界面进行配置

---

## 启动应用

### 方式一：一键启动（推荐开发使用）

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

### 1. 文档管理与知识图谱

- **文档上传与管理**
  - 支持 PPTX、PDF 格式文档上传
  - 单文件最大 50MB，每个对话最多 20 个文件
  - 批量上传，自动创建或指定对话

- **智能知识抽取**
  - 基于 LightRAG 自动提取实体和关系
  - 并行处理，自动合并重复实体
  - 支持多种实体类型（概念、人物、组织、地点等）

- **知识图谱可视化**
  - 交互式图谱展示（Cytoscape.js）
  - 节点和边详情查看，支持过滤、搜索和缩放
  - 实体来源文档追踪

- **文档可视化浏览**
  - PPTX 幻灯片浏览，PDF 文档浏览
  - 文本高亮，图片和表格渲染

### 2. 智能问答

- **多模式查询**
  - naive：纯向量相似度检索
  - local：基于局部知识图谱的子图检索
  - global：基于全局知识图谱的关系检索
  - mix：混合检索（推荐）

- **对话管理**
  - 多轮对话，保持上下文
  - 引用来源展示
  - 多对话独立工作空间

### 3. 试题生成

- **样本试题管理**
  - 支持 PDF/DOCX/TXT 格式样本上传
  - 自动解析样本结构（题型、难度、知识点）
  - 样本状态跟踪（pending/processing/completed）

- **AI 智能出题**
  - Agent 链式处理（A→F）：
    - Agent A：数据准备与文本提取
    - Agent B：知识点分析与建模
    - Agent C：题型与难度分布建模
    - Agent D：样本试卷结构解析
    - Agent E：基于知识图谱生成题目
    - Agent F：质量控制（语言统一、覆盖率、去重）
  - 自动生成多种题型（选择题、简答题、计算题等）
  - 知识点覆盖度分析

### 4. 智能批改

- **学生答卷处理**
  - 支持 PDF/DOCX/TXT 格式答卷上传
  - 自动解析答案（支持多种格式：Q001、GEN_001、数字序号等）
  - 智能匹配题目 ID

- **自动评分与反馈**
  - Agent G：逐题批改，生成评分和反馈
  - 评分报告（每题得分、反馈、问题点、改进建议）
  - 整体质量分析（平均分、知识点掌握情况）

- **学习建议**
  - Agent H：基于批改结果生成个性化学习建议
  - 薄弱知识点识别与推荐

## 项目特性

### 1. 对话隔离架构
- **独立工作空间**: 每个对话（conversation）拥有完全独立的数据存储空间
- **知识图谱隔离**: 不同对话之间的知识图谱完全独立，互不干扰
- **灵活管理**: 支持创建、删除、切换对话，便于管理多个项目或课程

### 2. 智能知识抽取流程
- **分块处理**: 文档自动分块（默认 600 tokens，重叠 50 tokens）
- **并行提取**: 多个 Chunk 并行调用 LLM 提取实体和关系
- **智能合并**: 自动识别并合并相同实体，生成综合描述
- **关系补全**: 处理关系时自动创建缺失的实体节点

### 3. 多模式查询系统
- **naive 模式**: 纯向量相似度检索，适合简单查询
- **local 模式**: 基于局部知识图谱的子图检索
- **global 模式**: 基于全局知识图谱的关系检索
- **mix 模式**: 混合多种检索方式，提供最全面的答案（推荐）

### 4. 实时处理监控
- **分阶段进度**: 显示分块、存储、提取、合并各阶段进度
- **状态跟踪**: 实时更新文档处理状态（pending/processing/completed/failed）
- **错误提示**: 详细的错误信息展示，便于问题排查

### 5. 高性能异步架构
- **异步处理**: 文档上传后立即返回，后台异步处理
- **并发控制**: 可配置的并发数，平衡性能和资源使用
- **非阻塞 API**: 所有耗时操作均为异步，不阻塞请求

### 6. 灵活的存储方案
- **开发环境**: 使用 JSON 文件和 GraphML 文件存储（零配置）
- **生产环境**: 支持 PostgreSQL、Neo4j、MongoDB、Milvus 等专业数据库
- **数据持久化**: 所有数据自动持久化到磁盘，支持多进程访问

### 7. Agent 链式处理架构
- **模块化设计**: 8 个独立 Agent，各司其职
- **依赖管理**: 自动处理 Agent 依赖关系，按序执行
- **状态共享**: 通过 shared_state 实现 Agent 间数据传递
- **可扩展性**: 易于添加新的 Agent 或修改处理流程

### 8. 教育场景优化
- **完整教学闭环**: 文档上传 → 知识抽取 → 试题生成 → 学生答题 → 自动批改 → 学习建议
- **知识图谱驱动**: 基于知识图谱生成高质量题目
- **智能质量控制**: 自动检测重复题、语言统一、知识点覆盖

## 技术栈

### 后端
- **FastAPI** - 高性能异步 Web 框架
- **LightRAG** - 知识图谱构建和检索增强生成框架
- **NetworkX** - 图数据结构存储（GraphML 格式）
- **pdfplumber / PyMuPDF** - PDF 文档解析
- **python-pptx** - PPTX 文档解析
- **Pillow** - 图片处理和渲染
- **Gitee OCR** - PDF OCR 识别（可选，支持中文识别）

### 前端
- **Vue 3** - 渐进式前端框架（Composition API）
- **Element Plus** - 企业级 UI 组件库
- **Pinia** - 现代化状态管理
- **Vue Router** - 单页应用路由管理
- **Cytoscape.js** - 知识图谱可视化引擎
- **Axios** - HTTP 客户端库
- **Vite** - 快速的前端构建工具

### 存储架构
- **KV 存储**: JSON 文件存储（开发环境）
- **向量存储**: NanoVectorDB（轻量级向量数据库）
- **图存储**: NetworkX（GraphML 文件存储）
- **文档状态**: JSON 文件存储

### LLM 集成
- 支持 OpenAI 兼容 API（如硅基流动、DeepSeek 等）
- 支持 Ollama 本地模型
- 可配置的 Embedding 模型

## Agent 模式技术说明（简要）

Agent 模式基于 **OpenAI 兼容的 tools / function calling 能力** 实现，通过结构化的工具定义，让后端业务函数可以被大模型“感知”和调用，整体流程如下：

1. **工具注册**：在后端通过 `ToolRegistry` 注册多个工具（如 `generate_mindmap`、`query_knowledge_graph`、`list_documents`），并为每个工具定义名称、描述和参数 JSON Schema。
2. **暴露给 LLM**：在调用 LLM 的请求中，通过 `tools` 字段将所有可用工具的信息传给模型，并使用 `tool_choice=auto` 让模型根据用户需求自动选择是否调用工具。
3. **模型决定工具调用**：当模型认为需要调用工具时，会返回结构化的 `tool_calls` 字段（包含要调用的工具名和参数 JSON 字符串），而不是普通自然语言文本。
4. **后端执行与二次调用**：后端解析 `tool_calls`，执行对应的 Python 处理函数，获得结果后以 `tool` 消息的形式回传给 LLM，随后再次调用 LLM 生成面向用户的自然语言最终回答。

当前 Agent 模式主要围绕考试与教学场景，重点支持 **文档列表获取、知识图谱查询和思维导图生成** 三类工具，后续可以按相同方式扩展新的工具和能力。

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
- `app/agents/` - Agent 链式处理模块
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

