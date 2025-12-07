"""
Agent 核心服务模块

本模块实现了基于 LLM Function Calling 的智能 Agent 系统，支持：
- 工具注册和管理
- LLM 工具调用识别和执行
- 工具结果处理和最终回答生成
- 流式响应支持

主要类：
    AgentService: Agent 核心服务类，负责处理用户查询、工具调用和 LLM 交互

使用示例：
    ```python
    agent_service = AgentService()
    
    async for chunk in agent_service.process_user_query(
        conversation_id="abc123",
        user_query="请生成思维导图"
    ):
        if chunk["type"] == "tool_result":
            print(f"工具执行结果: {chunk}")
        elif chunk["type"] == "response":
            print(f"LLM 回答: {chunk['content']}")
    ```

注意事项：
    - conversation_id 会自动注入到所有工具调用中，LLM 不需要提供此参数
    - 工具执行结果会自动发送回 LLM 生成最终回答
    - 所有消息的 content 字段必须是字符串类型（不能是 None）
"""
import json
import re
from typing import Dict, List, Optional, AsyncIterator, Any
from app.services.agent.tool_registry import ToolRegistry
from app.services.agent.tool_executor import ToolExecutor
from app.services.agent.tools.mindmap_tool import MINDMAP_TOOL
from app.services.agent.tools.query_tool import QUERY_TOOL
from app.services.agent.tools.list_documents_tool import LIST_DOCUMENTS_TOOL
from app.services.lightrag_service import LightRAGService
from app.services.memory_service import MemoryService
import app.config as config
import aiohttp


class AgentService:
    """Agent 核心服务"""
    
    def __init__(self):
        self.tool_registry = ToolRegistry()
        self.tool_executor = ToolExecutor(self.tool_registry)
        self._register_default_tools()
    
    def _register_default_tools(self):
        """注册默认工具"""
        self.tool_registry.register(MINDMAP_TOOL)
        self.tool_registry.register(QUERY_TOOL)
        self.tool_registry.register(LIST_DOCUMENTS_TOOL)
        print(f"📦 Agent 服务初始化完成，已注册 {len(self.tool_registry.tools)} 个工具")
    
    def _build_agent_system_prompt(self) -> str:
        """构建 Agent 系统提示词"""
        tools_description = []
        for tool in self.tool_registry.list_tools():
            tools_description.append(f"- {tool.name}: {tool.description}")
        
        return f"""你是一个智能助手，可以帮助用户完成各种任务。

你可以使用以下工具：
{chr(10).join(tools_description)}

基本使用规则：
1. 根据用户的需求，智能选择合适的工具
2. 如果用户明确要求执行某个操作（如"生成思维导图"、"画脑图"等），使用 generate_mindmap 工具, 若指名具体文档, 需要注意应该查询文档列表并注入文档参数
3. 如果用户想要查询文档内容，使用 query_knowledge_graph 工具
4. 如果用户想要查看文档列表（如"列出所有文档"、"显示文档"等），使用 list_documents 工具
5. 不要向用户透露工具名称，用自然语言描述操作 仅在必要时调用工具 如果任务简单或已知答案，直接回答，无需调用工具
6. **工具调用后，如果结果提示需要进一步操作，可以继续调用其他工具**
7. **只有在完成所有必要的工具调用后，才生成最终回答**
8. 工具调用后，将结果整合到回答中，以自然的方式呈现给用户

搜索和阅读原则:
- 不确定时先收集信息（搜索、读取文件等）
- 优先通过工具获取信息，而非直接询问用户
- 语义搜索后如结果不完整，继续搜索

参数使用原则:
- 仅在有相关工具时调用
- 确保提供必需参数，或可从上下文合理推断
- 如果缺少必需参数，询问用户
- 如果用户提供了具体值（如引号中的值），必须完全按该值使用
- 不要为可选参数编造值或询问

工具使用原则:
- 当用户提到"生成思维导图"、"生成脑图"、"画思维导图"等关键词时，必须使用 generate_mindmap 工具
- **conversation_id 参数会自动注入，你不需要也不应该在工具参数中提供 conversation_id**
- 调用工具时，只需要提供其他参数（如 document_ids、query、mode 等）
- 工具执行后，结果会自动返回给你，你需要用自然语言向用户解释结果

工具调用示例：
- 生成思维导图：调用 generate_mindmap，参数可以为空 {{}} 或指定文档 {{"document_ids": ["file_id1", "file_id2"]}}（不要包含 conversation_id）
  **重要：document_ids 必须使用 file_id（文档ID），而不是 filename（文件名）。可以通过 list_documents 工具获取每个文档的 file_id。**
- 查询知识图谱：调用 query_knowledge_graph，参数 {{"query": "用户的问题", "mode": "mix"}}（不要包含 conversation_id）


信息来源标注要求
1. 回答正文中，所有来自工具结果的重要信息都要用方括号编号标记，如 `[1]`、`[2]`、`[3]`，按首次出现顺序递增；同一信息如果依赖多个来源，可写成 `[1,2]`。
2. 回答末尾必须添加一个 **References** 部分，格式示例：
   ## References
   
   [1] [文档] 原文内容
   [2] [知识图谱] 实体/关系的原始描述, 需分类成实体或者关系,例如 "[知识图谱]实体: xxx" / "[知识图谱]关系: xxx" 

3. 来源类型约定：
   - 来自文档文本块（chunks）的内容标记为 `[文档]`；
   - 来自实体、关系等结构化信息标记为 `[知识图谱]`；

4. 严格依据原文：
   - 事实性信息必须直接或间接来源于工具返回的数据，不能编造；
   - 如果工具结果中没有找到相关信息，要明确说明“在当前文档/知识图谱中未找到相关内容”，不要自创答案。

关于文档ID的说明：
- **file_id（文档ID）**：每个文档的唯一标识符，格式如 "abc123-def456-ghi789"
- **filename（文件名）**：文档的显示名称，如 "01 - Introduction.pdf"
- **重要**：在调用 generate_mindmap 时，document_ids 参数必须使用 file_id，不能使用 filename
- 如果不知道 file_id，先调用 list_documents 工具查看文档列表，每个文档都会显示其 file_id

格式检查：在生成最终回答前，请确认：
- 正文中所有来源于文档的信息都有引用编号 `[X]`
- 末尾有完整的 References 部分
- 每个引用都标注了来源类型（`[文档]` 或 `[知识图谱]`）
- 每个引用都包含了可追溯的原文内容
- 对于数学公式, 行内公式用 $...$ 块级公式用 $$...$$
"""
    
    async def process_user_query(
        self,
        conversation_id: str,
        user_query: str,
        conversation_history: Optional[List[Dict]] = None,
        max_rounds: int = 15
    ) -> AsyncIterator[Dict[str, Any]]:
        """处理用户查询（Agent模式，支持多轮工具调用）
        
        Args:
            conversation_id: 对话ID
            user_query: 用户查询
            conversation_history: 对话历史
            max_rounds: 最大工具调用轮次（默认5轮）
            
        Yields:
            流式响应数据
        """
        # 1. 获取工具列表（转换为 Function Calling 格式）
        functions = self.tool_registry.to_function_calling_format()
        
        # 2. 构建系统提示词
        system_prompt = self._build_agent_system_prompt()
        
        # 3. 获取历史对话
        if conversation_history is None:
            memory_service = MemoryService()
            conversation_history = memory_service.get_recent_history(
                conversation_id,
                max_turns=3,
                max_tokens_per_message=500
            )
        
        # 4. 多轮工具调用循环
        round_count = 0
        current_messages = []
        
        # 添加历史对话到当前消息列表
        if conversation_history:
            current_messages.extend(conversation_history)
        
        # 添加用户查询
        current_messages.append({"role": "user", "content": user_query})
        
        while round_count < max_rounds:
            round_count += 1
            print(f"🔄 [Agent] 第 {round_count} 轮工具调用（最大 {max_rounds} 轮）")
            print(f"📨 [Agent] 当前消息列表长度: {len(current_messages)}")
            
            # 调用 LLM（支持 Function Calling）
            tool_calls_buffer = []
            accumulated_content = ""
            has_tool_calls = False
            
            async for chunk in self._call_llm_with_tools_round(
                conversation_id,
                system_prompt,
                current_messages,
                functions
            ):
                # 检查是否是工具调用
                if chunk.get("type") == "tool_call":
                    tool_calls_buffer.append(chunk.get("tool_call"))
                    has_tool_calls = True
                    # 立即 yield 工具调用，让前端知道工具调用的时间点
                    yield chunk
                elif chunk.get("type") == "response":
                    accumulated_content += chunk.get("content", "")
                    yield chunk
                else:
                    yield chunk
    
            # 如果没有工具调用，生成最终回答并退出
            if not has_tool_calls or not tool_calls_buffer:
                print(f"✅ [Agent] 没有更多工具调用，生成最终回答")
                # 如果 LLM 已经生成了文本内容，说明它已经回答了，不需要继续
                if accumulated_content:
                    print(f"💬 [Agent] LLM 已生成文本回答: {accumulated_content[:100]}...")
                break
            
            # 执行工具
            print(f"🔧 [Agent] 执行 {len(tool_calls_buffer)} 个工具调用")
            
            # 调试：打印 tool_calls_buffer 的原始内容
            print(f"🔍 [Agent] tool_calls_buffer 原始内容:")
            for i, tc in enumerate(tool_calls_buffer):
                print(f"  tool_call[{i}]: {tc}")
                if isinstance(tc, dict):
                    print(f"    id={tc.get('id')}, id类型={type(tc.get('id')).__name__}")
                    print(f"    type={tc.get('type')}, type类型={type(tc.get('type')).__name__}")
                    func = tc.get('function', {})
                    print(f"    function.name={func.get('name')}, name类型={type(func.get('name')).__name__}")
                    print(f"    function.arguments={func.get('arguments')[:100] if func.get('arguments') else None}, arguments类型={type(func.get('arguments')).__name__}")
            
            tool_results = []
            
            # 验证并修复 tool_calls_buffer 的格式（确保 arguments 是字符串）
            validated_tool_calls = []
            for tool_call in tool_calls_buffer:
                if not isinstance(tool_call, dict):
                    continue
                
                # 确保所有字段都是字符串类型
                tool_call_id = tool_call.get("id")
                if tool_call_id is None:
                    tool_call_id = ""
                elif not isinstance(tool_call_id, str):
                    tool_call_id = str(tool_call_id) if tool_call_id else ""
                
                tool_call_type = tool_call.get("type", "function")
                if not isinstance(tool_call_type, str):
                    tool_call_type = str(tool_call_type) if tool_call_type else "function"
                
                function = tool_call.get("function", {})
                if not isinstance(function, dict):
                    continue
                
                function_name = function.get("name", "")
                if not isinstance(function_name, str):
                    function_name = str(function_name) if function_name else ""
                
                # 关键：确保 arguments 是字符串
                function_arguments = function.get("arguments", "{}")
                if not isinstance(function_arguments, str):
                    # 如果是字典，转换为 JSON 字符串
                    if isinstance(function_arguments, dict):
                        function_arguments = json.dumps(function_arguments, ensure_ascii=False)
                    else:
                        function_arguments = str(function_arguments) if function_arguments is not None else "{}"
                
                # 如果 function_name 存在，即使 id 为空也保留（会在后面生成临时 id）
                if function_name:
                    # 如果 id 为空，生成一个临时 id（使用索引和时间戳）
                    if not tool_call_id:
                        import time
                        tool_call_id = f"call_{len(validated_tool_calls)}_{int(time.time() * 1000)}"
                        print(f"⚠️ [Agent] tool_call id 为空，生成临时 id: {tool_call_id}")
                    
                    validated_tool_calls.append({
                        "id": tool_call_id,
                        "type": tool_call_type,
                        "function": {
                            "name": function_name,
                            "arguments": function_arguments
                        }
                    })
                else:
                    print(f"⚠️ [Agent] 跳过无效的 tool_call: function_name 为空")
            
            assistant_message = {
                "role": "assistant",
                "content": accumulated_content if accumulated_content else "",
                "tool_calls": validated_tool_calls
            }
            current_messages.append(assistant_message)
            print(f"✅ [Agent] 添加 assistant 消息，包含 {len(validated_tool_calls)} 个工具调用")
            for i, tc in enumerate(validated_tool_calls):
                args = tc.get("function", {}).get("arguments", "")
                print(f"  工具调用[{i}]: id={tc.get('id')}, name={tc.get('function', {}).get('name')}, arguments类型={type(args).__name__}, arguments长度={len(str(args))}")
            
            # 执行工具调用，并正确匹配 tool_call_id
            # 注意：tool_call 事件已经在流式解析时 yield 了，这里不需要重复 yield
            # 使用 validated_tool_calls 而不是 tool_calls_buffer，确保 id 正确
            tool_call_index = 0
            async for result in self._execute_tool_calls(
                validated_tool_calls,
                conversation_id
            ):
                # 先 yield 给前端（用于实时显示）
                yield result
                
                # 收集工具结果
                if result["type"] == "tool_result":
                    tool_results.append(result)
                    
                    # 从 validated_tool_calls 中获取对应的 tool_call_id
                    tool_call_id = ""
                    if tool_call_index < len(validated_tool_calls):
                        tool_call = validated_tool_calls[tool_call_index]
                        tool_call_id = tool_call.get("id", "")
                        print(f"🔗 [Agent] 工具调用 ID: {tool_call_id}, 工具名: {result.get('tool_name')}")
                    else:
                        print(f"⚠️ [Agent] 警告: tool_call_index ({tool_call_index}) 超出 validated_tool_calls 长度 ({len(validated_tool_calls)})")
                    
                    # 添加 tool 消息到当前消息列表
                    tool_result_content = self._format_tool_result(result.get("result", {}))
                    tool_message = {
                        "role": "tool",
                        "content": tool_result_content,
                        "tool_call_id": tool_call_id
                    }
                    current_messages.append(tool_message)
                    print(f"📝 [Agent] 添加 tool 消息到历史，tool_call_id={tool_call_id}, content长度={len(tool_result_content)}")
                    tool_call_index += 1
                elif result["type"] == "tool_error":
                    # 从 validated_tool_calls 中获取对应的 tool_call_id
                    tool_call_id = ""
                    if tool_call_index < len(validated_tool_calls):
                        tool_call = validated_tool_calls[tool_call_index]
                        tool_call_id = tool_call.get("id", "")
                    
                    tool_message = {
                        "role": "tool",
                        "content": f"工具执行失败: {result.get('message', '')}",
                        "tool_call_id": tool_call_id
                    }
                    current_messages.append(tool_message)
                    print(f"❌ [Agent] 添加 tool 错误消息到历史，tool_call_id={tool_call_id}")
                    tool_results.append(result)  # 收集错误结果，确保循环继续
                    tool_call_index += 1
            
            # 如果没有工具结果，退出循环
            if not tool_results:
                print(f"⚠️ [Agent] 没有工具执行结果，退出循环")
                break
            
            print(f"✅ [Agent] 工具执行完成，当前消息列表长度: {len(current_messages)}")
            print(f"🔄 [Agent] 准备进行下一轮工具调用...")
        
        if round_count >= max_rounds:
            print(f"⚠️ [Agent] 达到最大工具调用轮次限制 ({max_rounds} 轮)")
            yield {
                "type": "error",
                "content": f"达到最大工具调用轮次限制 ({max_rounds} 轮)，请简化您的请求"
            }
    
    async def _call_llm_with_tools_round(
        self,
        conversation_id: str,
        system_prompt: str,
        messages: List[Dict],
        functions: List[Dict]
    ) -> AsyncIterator[Dict[str, Any]]:
        """单轮 LLM 调用（支持 Function Calling）
        
        Args:
            conversation_id: 对话ID
            system_prompt: 系统提示词
            messages: 消息列表（包含历史对话和用户查询）
            functions: 工具定义列表
            
        Yields:
            流式响应数据
        """
        # 构建消息列表
        llm_messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 添加消息（确保所有 content 都是字符串）
        for msg in messages:
            cleaned_msg = msg.copy()
            role = cleaned_msg.get("role")
            
            # 确保 content 字段存在且为字符串
            if "content" not in cleaned_msg:
                cleaned_msg["content"] = ""
            elif cleaned_msg.get("content") is None:
                cleaned_msg["content"] = ""
            elif not isinstance(cleaned_msg.get("content"), str):
                cleaned_msg["content"] = str(cleaned_msg["content"])
            
            # 对于 tool 消息，确保 tool_call_id 存在
            if role == "tool":
                if "tool_call_id" not in cleaned_msg or not cleaned_msg.get("tool_call_id"):
                    continue
            
            # 对于 assistant 消息，如果有 tool_calls，确保格式正确
            if role == "assistant" and "tool_calls" in cleaned_msg:
                tool_calls = cleaned_msg.get("tool_calls", [])
                if not isinstance(tool_calls, list) or not tool_calls:
                    cleaned_msg.pop("tool_calls", None)
                else:
                    # 验证并修复每个 tool_call 的字段类型
                    valid_tool_calls = []
                    for tool_call in tool_calls:
                        if not isinstance(tool_call, dict):
                            continue
                        
                        # 确保 id 是字符串
                        tool_call_id = tool_call.get("id", "")
                        if not isinstance(tool_call_id, str):
                            tool_call_id = str(tool_call_id) if tool_call_id else ""
                        
                        # 确保 type 是字符串
                        tool_call_type = tool_call.get("type", "function")
                        if not isinstance(tool_call_type, str):
                            tool_call_type = str(tool_call_type) if tool_call_type else "function"
                        
                        # 确保 function 存在且是字典
                        function = tool_call.get("function", {})
                        if not isinstance(function, dict):
                            continue
                        
                        # 确保 function.name 是字符串
                        function_name = function.get("name", "")
                        if not isinstance(function_name, str):
                            function_name = str(function_name) if function_name else ""
                        
                        # 确保 function.arguments 是字符串（关键修复点）
                        function_arguments = function.get("arguments", "{}")
                        if not isinstance(function_arguments, str):
                            # 如果是字典，转换为 JSON 字符串
                            if isinstance(function_arguments, dict):
                                function_arguments = json.dumps(function_arguments, ensure_ascii=False)
                            else:
                                function_arguments = str(function_arguments) if function_arguments is not None else "{}"
                        
                        # 如果关键字段为空，跳过此 tool_call
                        if not tool_call_id or not function_name:
                            continue
                        
                        # 构建有效的 tool_call
                        valid_tool_calls.append({
                            "id": tool_call_id,
                            "type": tool_call_type,
                            "function": {
                                "name": function_name,
                                "arguments": function_arguments
                            }
                        })
                    
                    # 更新 cleaned_msg 中的 tool_calls
                    if valid_tool_calls:
                        cleaned_msg["tool_calls"] = valid_tool_calls
                        print(f"🔍 [Agent] 验证 assistant 消息的 tool_calls: {len(valid_tool_calls)} 个有效调用")
                        for i, tc in enumerate(valid_tool_calls):
                            args = tc.get("function", {}).get("arguments", "")
                            print(f"  验证后工具调用[{i}]: id={tc.get('id')}, name={tc.get('function', {}).get('name')}, arguments类型={type(args).__name__}, arguments长度={len(str(args))}")
                    else:
                        # 如果没有有效的 tool_calls，移除该字段
                        cleaned_msg.pop("tool_calls", None)
                        print(f"⚠️ [Agent] assistant 消息的 tool_calls 验证后全部无效，已移除")
            
            llm_messages.append(cleaned_msg)
        
        # 使用聊天场景的配置
        from app.services.config_service import config_service
        chat_config = config_service.get_config("chat")
        binding = chat_config.get("binding", config.settings.chat_llm_binding)
        model = chat_config.get("model", config.settings.chat_llm_model)
        api_key = chat_config.get("api_key", config.settings.chat_llm_binding_api_key)
        host = chat_config.get("host", config.settings.chat_llm_binding_host)
        
        # 调用 LLM API
        api_url = f"{host}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": llm_messages,
            "stream": True,
            "temperature": 0.7
        }
        
        # 只有当有工具时才添加 tools 和 tool_choice
        if functions and len(functions) > 0:
            payload["tools"] = functions
            payload["tool_choice"] = "auto"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        # 401 错误：API Key 无效
                        if response.status == 401:
                            error_msg = "API Key 无效或已过期，请在设置中检查并更新 API Key"
                        else:
                            error_msg = f"LLM API 错误: {response.status}, {error_text}"
                        yield {"type": "error", "content": error_msg}
                        return
                    
                    accumulated_content = ""
                    tool_calls_buffer = []
                    finished_tool_calls = False
                    yielded_tool_call_indices = set()  # 跟踪已 yield 的 tool_call index
                    
                    async for line in response.content:
                        if not line:
                            continue
                        
                        line_text = line.decode('utf-8')
                        for chunk in line_text.split('\n'):
                            if not chunk.strip() or chunk.startswith(':'):
                                continue
                            
                            if chunk.startswith('data: '):
                                chunk = chunk[6:]
                            
                            if chunk.strip() == '[DONE]':
                                # 处理剩余的工具调用（只处理那些还没有 yield 过的）
                                if tool_calls_buffer and not finished_tool_calls:
                                    finished_tool_calls = True
                                    import time
                                    print(f"🔍 [Agent] [DONE] 时，检查 tool_calls_buffer，已 yield 的索引: {yielded_tool_call_indices}")
                                    for i, tool_call in enumerate(tool_calls_buffer):
                                        if tool_call.get("function", {}).get("name") and i not in yielded_tool_call_indices:
                                            # 确保 tool_call 有有效的 id
                                            if not tool_call.get("id"):
                                                tool_call["id"] = f"call_{i}_{int(time.time() * 1000)}"
                                                print(f"⚠️ [Agent] [DONE] 时，tool_call id 为空，生成临时 id: {tool_call['id']}")
                                            print(f"🚀 [Agent] [DONE] 时 yield tool_call: {tool_call['function']['name']}, id: {tool_call.get('id')}, index: {i}")
                                            yield {
                                                "type": "tool_call",
                                                "tool_call": tool_call
                                            }
                                            yielded_tool_call_indices.add(i)
                                return
                            
                            try:
                                data = json.loads(chunk)
                                choices = data.get('choices', [])
                                if choices:
                                    delta = choices[0].get('delta', {})
                                    
                                    # 检查是否是工具调用
                                    if 'tool_calls' in delta and delta['tool_calls']:
                                        tool_calls = delta['tool_calls']
                                        for tool_call_delta in tool_calls:
                                            index = tool_call_delta.get('index', 0)
                                            
                                            # 确保 tool_calls_buffer 有足够的元素
                                            while len(tool_calls_buffer) <= index:
                                                tool_calls_buffer.append({
                                                    "id": "",
                                                    "type": "function",
                                                    "function": {"name": "", "arguments": ""}
                                                })
                                            
                                            tool_call = tool_calls_buffer[index]
                                            
                                            # 更新工具调用信息
                                            if 'id' in tool_call_delta:
                                                tool_call["id"] = tool_call_delta['id']
                                                # print(f"🔍 [Agent] 收到 tool_call id: {tool_call_delta['id']}, index: {index}")  # 调试日志已关闭
                                            
                                            if 'function' in tool_call_delta:
                                                func_delta = tool_call_delta['function']
                                                
                                                # 处理 name
                                                if 'name' in func_delta and func_delta['name']:
                                                    tool_call["function"]["name"] = func_delta['name']
                                                    print(f"🔍 [Agent] 收到 tool_call name: {func_delta['name']}, index: {index}, 已yield: {index in yielded_tool_call_indices}")
                                                    
                                                    # 一旦检测到 tool_call 的 name，立即 yield（如果还没有 yield 过）
                                                    if index not in yielded_tool_call_indices:
                                                        # 确保 tool_call 有有效的 id
                                                        if not tool_call.get("id"):
                                                            import time
                                                            tool_call["id"] = f"call_{index}_{int(time.time() * 1000)}"
                                                            print(f"⚠️ [Agent] tool_call id 为空，生成临时 id: {tool_call['id']}")
                                                        
                                                        yielded_tool_call_indices.add(index)
                                                        print(f"🚀 [Agent] 立即 yield tool_call: {func_delta['name']}, id: {tool_call.get('id')}, index: {index}")
                                                        
                                                        # 立即 yield 工具调用，让前端立即显示
                                                        yield {
                                                            "type": "tool_call",
                                                            "tool_call": tool_call.copy()  # 使用副本，避免后续修改影响
                                                        }
                                                
                                                # 处理 arguments（可能 name 和 arguments 同时到达）
                                                if 'arguments' in func_delta and func_delta['arguments']:
                                                    tool_call["function"]["arguments"] += func_delta['arguments']
                                                    # 如果 name 已经设置但还没有 yield（可能 name 和 arguments 同时到达，但 name 先处理）
                                                    if tool_call.get("function", {}).get("name") and index not in yielded_tool_call_indices:
                                                        # 确保 tool_call 有有效的 id
                                                        if not tool_call.get("id"):
                                                            import time
                                                            tool_call["id"] = f"call_{index}_{int(time.time() * 1000)}"
                                                            print(f"⚠️ [Agent] 通过 arguments 检测到 tool_call，id 为空，生成临时 id: {tool_call['id']}")
                                                        
                                                        yielded_tool_call_indices.add(index)
                                                        print(f"🚀 [Agent] 通过 arguments 立即 yield tool_call: {tool_call['function']['name']}, id: {tool_call.get('id')}, index: {index}")
                                                        
                                                        # 立即 yield 工具调用，让前端立即显示
                                                        yield {
                                                            "type": "tool_call",
                                                            "tool_call": tool_call.copy()
                                                        }
                                    
                                    # 正常文本内容
                                    if 'content' in delta:
                                        content = delta.get('content', '')
                                        if content:
                                            accumulated_content += content
                                            yield {
                                                "type": "response",
                                                "content": content
                                            }
                            
                            except json.JSONDecodeError:
                                continue
                    
                    # 流式结束后，处理工具调用（只处理那些还没有 yield 过的）
                    if tool_calls_buffer and not finished_tool_calls:
                        finished_tool_calls = True
                        import time
                        for i, tool_call in enumerate(tool_calls_buffer):
                            if tool_call.get("function", {}).get("name") and i not in yielded_tool_call_indices:
                                # 确保 tool_call 有有效的 id
                                if not tool_call.get("id"):
                                    tool_call["id"] = f"call_{i}_{int(time.time() * 1000)}"
                                    print(f"⚠️ [Agent] 流式响应结束时，tool_call id 为空，生成临时 id: {tool_call['id']}")
                                yield {
                                    "type": "tool_call",
                                    "tool_call": tool_call
                                }
                                yielded_tool_call_indices.add(i)
        
        except Exception as e:
            yield {
                "type": "error",
                "content": f"调用 LLM 时出错: {str(e)}"
            }
    
    async def _call_llm_with_tools(
        self,
        conversation_id: str,
        user_query: str,
        system_prompt: str,
        functions: List[Dict],
        conversation_history: Optional[List[Dict]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """调用 LLM (支持 Function Calling) - 兼容旧接口
        
        注意：此方法已被 _call_llm_with_tools_round 替代
        """
        # 构建消息列表
        messages = []
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_query})
        
        # 调用新的单轮方法
        async for chunk in self._call_llm_with_tools_round(
            conversation_id,
            system_prompt,
            messages,
            functions
        ):
            yield chunk
    
    async def _generate_final_response(
        self,
        tool_calls_buffer: List[Dict],
        tool_results: List[Dict],
        system_prompt: str,
        conversation_history: Optional[List[Dict]],
        user_query: str,
        api_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """基于工具执行结果生成最终回答"""
        print(f"🔄 [Agent] 开始生成最终回答，工具结果数量: {len(tool_results)}")
        
        # 使用聊天场景的配置
        from app.services.config_service import config_service
        chat_config = config_service.get_config("chat")
        binding = chat_config.get("binding", config.settings.chat_llm_binding)
        model = chat_config.get("model", config.settings.chat_llm_model)
        api_key = chat_config.get("api_key", config.settings.chat_llm_binding_api_key)
        host = chat_config.get("host", config.settings.chat_llm_binding_host)
        
        # 如果未提供 api_url 和 headers，使用聊天配置
        if not api_url:
            api_url = f"{host}/chat/completions"
        if not headers:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

        # 1. 将工具结果格式化为 LLM 需要的 tool 消息
        tool_messages: List[Dict[str, Any]] = []
        tool_result_index = 0
        
        for i, tool_call in enumerate(tool_calls_buffer):
            func = tool_call.get("function", {})
            if not func.get("name"):
                continue
                                
            tool_call_id = tool_call.get("id") or f"call_{i}"
            if not isinstance(tool_call_id, str):
                tool_call_id = str(tool_call_id)
                                
            if tool_result_index < len(tool_results):
                tool_result = tool_results[tool_result_index]
                result_data = tool_result.get("result", {})
                result_content = self._format_tool_result(result_data)
                if not isinstance(result_content, str):
                    result_content = str(result_content) if result_content is not None else ""
                
                tool_messages.append(
                    {
                        "role": "tool",
                        "content": result_content,
                        "tool_call_id": tool_call_id,
                    }
                )
                tool_result_index += 1
                            
        # 2. 构建完整的消息历史（system + 历史对话 + 当前 user）
        complete_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
                            
        if conversation_history:
            for msg in conversation_history:
                cleaned_msg = msg.copy()
                role = cleaned_msg.get("role")
                
                # 确保 content 字段存在且为字符串
                content = cleaned_msg.get("content")
                if content is None:
                    cleaned_msg["content"] = ""
                elif not isinstance(content, str):
                    cleaned_msg["content"] = str(content)
                
                # 对于 tool 消息，确保 tool_call_id 存在且有效
                if role == "tool":
                    tool_call_id = cleaned_msg.get("tool_call_id")
                    if tool_call_id is None or (
                        isinstance(tool_call_id, str) and not tool_call_id.strip()
                    ):
                        print(
                            "⚠️ [Agent] 警告: 历史对话中的 tool 消息缺少或包含空的 tool_call_id，跳过此消息"
                        )
                        continue
                
                # 对于 assistant 消息，如果有 tool_calls，确保格式正确
                if role == "assistant" and "tool_calls" in cleaned_msg:
                    tool_calls = cleaned_msg.get("tool_calls", [])
                    if not isinstance(tool_calls, list):
                        print(
                            "⚠️ [Agent] 警告: 历史对话中的 assistant 消息的 tool_calls 不是列表，移除"
                        )
                        cleaned_msg.pop("tool_calls", None)
                    else:
                        valid_tool_calls: List[Dict[str, Any]] = []
                        for tc in tool_calls:
                            if not isinstance(tc, dict):
                                continue
                            if not tc.get("id"):
                                print(
                                    "⚠️ [Agent] 警告: 历史对话中的 tool_call 缺少 id，跳过"
                                )
                                continue
                            if tc.get("type") != "function":
                                print(
                                    "⚠️ [Agent] 警告: 历史对话中的 tool_call type 不正确，跳过"
                                )
                                continue
                            func = tc.get("function", {})
                            if not func.get("name"):
                                print(
                                    "⚠️ [Agent] 警告: 历史对话中的 tool_call function.name 缺失，跳过"
                                )
                                continue
                            if "arguments" not in func:
                                print(
                                    "⚠️ [Agent] 警告: 历史对话中的 tool_call function.arguments 缺失，跳过"
                                )
                                continue
                            valid_tool_calls.append(tc)
                        cleaned_msg["tool_calls"] = valid_tool_calls
                        if not valid_tool_calls:
                            cleaned_msg.pop("tool_calls", None)
                
                complete_messages.append(cleaned_msg)
                            
        # 添加当前用户查询
        complete_messages.append({"role": "user", "content": user_query})
                            
        # 3. 构建 assistant 的 tool_calls 消息
        tool_calls_list: List[Dict[str, Any]] = []
        for i, tool_call in enumerate(tool_calls_buffer):
            func = tool_call.get("function", {})
            if not func.get("name"):
                continue
            
            tool_call_id = tool_call.get("id") or f"call_{i}"
            if not isinstance(tool_call_id, str):
                tool_call_id = str(tool_call_id)
            
            function_name = func.get("name", "")
            if not isinstance(function_name, str):
                function_name = str(function_name)
            
            function_arguments = func.get("arguments", "{}")
            if not isinstance(function_arguments, str):
                function_arguments = (
                    str(function_arguments) if function_arguments is not None else "{}"
                )

            if not tool_call_id:
                import time

                tool_call_id = f"call_{i}_{int(time.time() * 1000)}"
            if not function_name:
                print("    ⚠️ 警告: function_name 为空，跳过此 tool_call")
                continue
            if not function_arguments:
                function_arguments = "{}"
            
            tool_calls_list.append(
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "arguments": function_arguments,
                    },
                }
            )
        
        if tool_calls_list:
            assistant_message = {
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls_list,
            }
            complete_messages.append(assistant_message)
        else:
            print("    ⚠️ 警告: tool_calls_list 为空，不添加 assistant 消息")
                            
        # 4. 添加工具结果消息
        complete_messages.extend(tool_messages)
        
        # 5. 打印调试信息（仅显示最后几条）
        print(f"📝 [Agent] 构建的消息历史（共 {len(complete_messages)} 条）:")
        start_index = max(0, len(complete_messages) - 3)
        for i, msg in enumerate(complete_messages[start_index:], start=start_index):
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                print(
                    f"  [{i}] tool: content_type={type(content).__name__}, "
                    f"tool_call_id={tool_call_id}, content_preview={str(content)[:100]}..."
                )
            elif role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                print(
                    f"  [{i}] assistant: content='{str(content)[:50]}...', tool_calls={len(tool_calls)}"
                )
                for j, tc in enumerate(tool_calls):
                    tc_id = tc.get("id")
                    tc_type = tc.get("type")
                    func = tc.get("function", {})
                    func_name = func.get("name")
                    func_args = func.get("arguments")
                    print(
                        f"    tool_call[{j}]: id={tc_id}, type={tc_type}, "
                        f"name={func_name}, args_type={type(func_args).__name__}"
                    )
            else:
                print(
                    f"  [{i}] {role}: content_type={type(content).__name__}, "
                    f"content_preview={str(content)[:50]}..."
                )
        
        # 6. 确保所有消息都有必需的字段
        validated_messages: List[Dict[str, Any]] = []
        for msg in complete_messages:
            role = msg.get("role")
            if role == "assistant" and "tool_calls" in msg:
                if "content" not in msg:
                    msg["content"] = ""
                tool_calls = msg.get("tool_calls", [])
                if not tool_calls:
                    print("    ⚠️ 警告: assistant 消息的 tool_calls 为空")
                else:
                    for tc in tool_calls:
                        if not tc.get("id"):
                            print("    ⚠️ 警告: tool_call 缺少 id")
                        if tc.get("type") != "function":
                            print(
                                f"    ⚠️ 警告: tool_call type 不正确: {tc.get('type')}"
                            )
                        func = tc.get("function", {})
                        if not func.get("name"):
                            print("    ⚠️ 警告: tool_call function.name 为空")
                        if "arguments" not in func:
                            print("    ⚠️ 警告: tool_call function.arguments 缺失")
            elif role == "tool":
                if "content" not in msg:
                    msg["content"] = ""
                tool_call_id = msg.get("tool_call_id")
                if "tool_call_id" not in msg:
                    print("    ⚠️ 警告: tool 消息缺少 tool_call_id 字段")
                elif not tool_call_id or (
                    isinstance(tool_call_id, str) and not tool_call_id.strip()
                ):
                    print(
                        f"    ⚠️ 警告: tool 消息的 tool_call_id 为空或无效: {repr(tool_call_id)}"
                    )
                    print("    ⚠️ 警告: 跳过无效的 tool 消息")
                    continue
                else:
                    if not isinstance(tool_call_id, str):
                        msg["tool_call_id"] = str(tool_call_id)
                        print("    ✅ 修复: tool_call_id 类型已转换为字符串")
            else:
                if "content" not in msg:
                    msg["content"] = ""
            
            validated_messages.append(msg)
        
        complete_messages = validated_messages
                            
        # 7. 构建最终 payload
        final_payload = {
            "model": model,
            "messages": complete_messages,
            "stream": True,
            "temperature": 0.7,
        }
        
        print("📦 [Agent] 最终 payload 结构:")
        print(f"  - model: {final_payload.get('model')}")
        print(f"  - messages count: {len(final_payload.get('messages', []))}")
        print(f"  - stream: {final_payload.get('stream')}")
        print(f"  - temperature: {final_payload.get('temperature')}")
        print(f"  - has tools: {'tools' in final_payload}")
        
        print("🚀 [Agent] 二次调用 LLM 生成最终回答...")
                            
        # 8. 流式调用 LLM 生成最终回答
        async with aiohttp.ClientSession() as final_session:
            async with final_session.post(
                api_url,
                headers=headers,
                json=final_payload,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as final_response:
                print(f"📡 [Agent] LLM 响应状态: {final_response.status}")
                if final_response.status == 200:
                    content_received = False
                    async for line in final_response.content:
                        if not line:
                            continue
                        
                        line_text = line.decode("utf-8")
                        for chunk in line_text.split("\n"):
                            if not chunk.strip() or chunk.startswith(":"):
                                continue
                            
                            if chunk.startswith("data: "):
                                chunk = chunk[6:]
                            
                            if chunk.strip() == "[DONE]":
                                return
                            
                            try:
                                data = json.loads(chunk)
                            except json.JSONDecodeError:
                                continue

                            choices = data.get("choices", [])
                            if not choices:
                                continue

                            delta = choices[0].get("delta", {})
                            if "content" not in delta:
                                continue

                            content = delta.get("content", "")
                            if not content:
                                continue

                            if not content_received:
                                print("✅ [Agent] 开始接收 LLM 最终回答内容")
                                content_received = True

                            yield {
                                "type": "response",
                                "content": content,
                            }
                else:
                    error_text = await final_response.text()
                    print(f"❌ [Agent] LLM 最终回答生成失败: {final_response.status}, {error_text}")
                    # 401 错误：API Key 无效
                    if final_response.status == 401:
                        error_msg = "API Key 无效或已过期，请在设置中检查并更新 API Key"
                    else:
                        error_msg = f"LLM API 错误: {final_response.status}, {error_text}"
                    yield {"type": "error", "content": error_msg}
    
    def _format_tool_result(self, result_data: Dict[str, Any]) -> str:
        """格式化工具执行结果为字符串，用于发送回 LLM
        
        Args:
            result_data: 工具执行结果（从 tool_executor.execute 返回的格式）
            
        Returns:
            格式化的字符串结果
        """
        status = result_data.get("status", "unknown")
        tool_result = result_data.get("result", {})  # 这是工具 handler 返回的原始结果
        
        if status == "success":
            # 成功时，提取关键信息
            if isinstance(tool_result, dict):
                # 提取主要信息
                message = tool_result.get("message", "执行成功")
                result_content = tool_result.get("result", "")
                mindmap_content = tool_result.get("mindmap_content", "")
                
                # 构建格式化结果
                formatted = f"执行成功。{message}"
                
                # 如果有实际结果内容，添加到格式化字符串中
                if result_content:
                    if isinstance(result_content, str):
                        formatted += f"\n\n查询结果：\n{result_content}"
                    else:
                        formatted += f"\n\n结果：{str(result_content)}"
                elif mindmap_content:
                    # 思维脑图内容（不完整显示，只提示）
                    formatted += f"\n\n思维脑图已生成，内容已保存。"
                
                return formatted
            else:
                return f"执行成功。结果：{str(tool_result)}"
        
        elif status == "error":
            # 失败时，返回错误信息
            error_msg = result_data.get("message", "执行失败")
            error_detail = result_data.get("error", "")
            if error_detail:
                return f"执行失败：{error_msg}\n错误详情：{error_detail}"
            return f"执行失败：{error_msg}"
        
        else:
            # 其他状态
            return f"执行状态：{status}\n结果：{json.dumps(result_data, ensure_ascii=False)}"
    
    async def _execute_tool_calls(
        self,
        tool_calls: List[Dict],
        conversation_id: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """执行工具调用"""
        for tool_call in tool_calls:
            if not tool_call.get("function", {}).get("name"):
                continue
            
            tool_name = tool_call["function"]["name"]
            arguments_str = tool_call["function"].get("arguments", "{}")
            
            # 如果参数为空，使用空字典
            if not arguments_str or arguments_str.strip() == "":
                arguments_str = "{}"
            
            try:
                # 解析参数
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError as e:
                yield {
                    "type": "tool_error",
                    "tool_name": tool_name,
                    "message": f"工具参数解析失败: {arguments_str}, 错误: {str(e)}"
                }
                continue
            
            # 执行工具
            result = await self.tool_executor.execute(
                tool_name,
                arguments,
                conversation_id
            )
            
            # 返回工具执行结果（包含参数信息，供前端显示）
            yield {
                "type": "tool_result",
                "tool_name": tool_name,
                "arguments": arguments,  # 添加参数信息
                "result": result
            }
            
            # 如果是思维脑图工具，还需要流式返回思维脑图内容
            if tool_name == "generate_mindmap" and result.get("status") == "success":
                mindmap_content = result.get("result", {}).get("mindmap_content")
                if mindmap_content:
                    yield {
                        "type": "mindmap_content",
                        "content": mindmap_content
                    }

