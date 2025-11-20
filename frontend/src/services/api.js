import axios from 'axios'
import { ElMessage } from 'element-plus'

// 创建 axios 实例
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 0,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  config => {
    // 开发环境下打印请求日志
    if (import.meta.env.DEV) {
      console.log(`[API Request] ${config.method?.toUpperCase()} ${config.url}`, config.data || config.params)
    }
    
    // 如果是文件上传，自动设置正确的 Content-Type
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type']
    }
    
    return config
  },
  error => {
    console.error('[API Request Error]', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  response => {
    // 开发环境下打印响应日志
    if (import.meta.env.DEV) {
      console.log(`[API Response] ${response.config.url}`, response.data)
    }
    
    // 直接返回 data，方便使用
    return response.data
  },
  error => {
    // 错误处理
    let errorMessage = '请求失败'
    
    if (error.response) {
      // 服务器返回了错误响应
      const status = error.response.status
      const data = error.response.data
      
      // 提取错误信息
      errorMessage = data?.detail || data?.message || `请求错误 (${status})`
      
      // 根据状态码显示不同的提示
      switch (status) {
        case 400:
          errorMessage = data?.detail || '请求参数错误'
          break
        case 401:
          errorMessage = '未授权，请重新登录'
          break
        case 403:
          errorMessage = '没有权限访问'
          break
        case 404:
          errorMessage = data?.detail || '资源不存在'
          break
        case 500:
          errorMessage = data?.detail || '服务器内部错误'
          break
        default:
          errorMessage = data?.detail || `服务器错误 (${status})`
      }
    } else if (error.request) {
      // 请求已发出，但没有收到响应
      errorMessage = '网络连接失败，请检查网络'
    } else {
      // 其他错误
      errorMessage = error.message || '请求失败'
    }
    
    // 显示错误提示
    ElMessage.error(errorMessage)
    
    // 开发环境下打印详细错误
    if (import.meta.env.DEV) {
      console.error('[API Error]', {
        message: errorMessage,
        error: error,
        response: error.response
      })
    }
    
    return Promise.reject(error)
  }
)

export { api }
