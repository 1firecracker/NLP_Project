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
  async queryStream(conversationId, query, mode = 'naive', onChunk) {
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/conversations/${conversationId}/query/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query,
        mode,
        stream: true
      })
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
            
            if (parsed.response) {
              // 调用回调函数处理数据块
              onChunk(parsed.response)
            } else if (parsed.warning) {
              // 处理警告消息（需要特殊样式）
              onChunk({ type: 'warning', content: parsed.warning })
            } else if (parsed.error) {
              throw new Error(parsed.error)
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
   */
  async saveMessage(conversationId, query, answer) {
    await api.post(`/api/conversations/${conversationId}/messages`, {
      query,
      answer
    })
  }
}

export default new ChatService()

