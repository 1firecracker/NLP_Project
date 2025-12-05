import { api } from './api'

/**
 * 对话/聊天服务
 */
class ChatService {
  /**
   * 流式查询（支持逐字显示）
   * @param {string} conversationId - 对话ID
   * @param {string} query - 查询文本
   * @param {string} mode - 查询模式（mix/local/global/naive）
   * @param {Function} onChunk - 接收到数据块时的回调函数
   */
  async queryStream(conversationId, query, mode = 'naive', agentIntent, onChunk) {
    const body = {
      query,
      mode,
      stream: true
    }
    
    // 如果检测到Agent意图，添加到请求体（保留参数以兼容未来扩展）
    if (agentIntent) {
      // 目前不需要额外参数，LLM会自动检测
    }
    
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/conversations/${conversationId}/query/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body)
    })
    
    if (!response.ok) {
      throw new Error(`查询失败: ${response.statusText}`)
    }
    
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    
    while (true) {
      const { done, value } = await reader.read()
      
      if (done) {
        break
      }
      
      // 解码数据块
      buffer += decoder.decode(value, { stream: true })
      
      // 处理完整的行（NDJSON格式）
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // 保留可能不完整的行
      
      for (const line of lines) {
        if (line.trim()) {
          try {
            const parsed = JSON.parse(line)
            
            if (parsed.response !== undefined) {
              // Agent 模式的响应内容（可能是字符串或对象）
              if (typeof parsed.response === 'string') {
                // 如果是字符串，转换为对象格式
                onChunk({ type: 'response', content: parsed.response })
              } else if (parsed.response && typeof parsed.response === 'object') {
                // 如果已经是对象，直接使用
              onChunk(parsed.response)
              } else {
                // 其他情况，作为字符串处理
                onChunk({ type: 'response', content: String(parsed.response) })
              }
            } else if (parsed.warning) {
              // 处理警告消息（需要特殊样式）
              onChunk({ type: 'warning', content: parsed.warning })
            } else if (parsed.tool_call) {
              // Agent 模式的工具调用开始
              // console.log('📥 [前端] 收到 tool_call 事件:', parsed.tool_call)
              onChunk({ type: 'tool_call', tool_call: parsed.tool_call })
            } else if (parsed.tool_result) {
              // Agent 模式的工具执行结果
              onChunk({ type: 'tool_result', tool_result: parsed.tool_result })
            } else if (parsed.tool_error) {
              // Agent 模式的工具执行错误
              onChunk({ type: 'tool_error', ...parsed.tool_error })
            } else if (parsed.mindmap_content) {
              // Agent 模式的思维脑图内容
              onChunk({ type: 'mindmap_content', content: parsed.mindmap_content })
            } else if (parsed.error) {
              onChunk({ type: 'error', content: parsed.error })
            }
          } catch (error) {
            console.error('解析流式响应失败:', line, error)
            // 继续处理其他行，不中断流
          }
        }
      }
    }
    
    // 处理剩余的缓冲数据
    if (buffer.trim()) {
      try {
        const parsed = JSON.parse(buffer)
        if (parsed.response) {
          onChunk(parsed.response)
        } else if (parsed.warning) {
          onChunk({ type: 'warning', content: parsed.warning })
        }
      } catch (error) {
        console.error('解析最终数据块失败:', buffer, error)
      }
    }
  }
  
  /**
   * 获取对话历史消息
   * @param {string} conversationId - 对话ID
   * @returns {Promise<Object>} 包含 messages 数组的对象
   */
  async getHistory(conversationId) {
    const response = await api.get(`/api/conversations/${conversationId}/messages`)
    return response
  }
  
  /**
   * 保存消息到后端
   * @param {string} conversationId - 对话ID
   * @param {string} query - 用户查询
   * @param {string} answer - AI回复
   * @param {Array} toolCalls - 工具调用信息（可选）
   * @param {Array} streamItems - 流式输出项（可选）
   */
  async saveMessage(conversationId, query, answer, toolCalls = null, streamItems = null) {
    await api.post(`/api/conversations/${conversationId}/messages`, {
      query,
      answer,
      tool_calls: toolCalls,
      stream_items: streamItems
    })
  }
}

export default new ChatService()

