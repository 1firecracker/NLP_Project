"""修复前端 ExerciseViewer.vue"""

filepath = r'c:\Users\19668\Desktop\workspace\NLP_Project\frontend\src\components\ExerciseViewer\ExerciseViewer.vue'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 替换 startGeneration 函数
old_func = '''const startGeneration = async () => {
  if (samples.value.length === 0) {
    ElMessage.warning('请先上传样本试题')
    return
  }

  generating.value = true
  generationStatus.value = '正在启动生成任务...'
  generationResult.value = null
  generatedQuestions.value = []

  try {
    const convId = conversation_id.value || 'default'

    // 1️⃣ 调用"生成题目"
    const res = await api.post(
      `/api/conversations/${convId}/exercises/generate`
    )

    // ⭐⭐ 修正点 #1：不要再用 res.data
    const data = res
    console.log("🔥 /generate 返回:", data)

    // ⭐⭐ 修正点 #2（可选，但建议）
    if (!data || typeof data.question_count === "undefined") {
      throw new Error("后端未返回 question_count")
    }

    generationResult.value = data
    generationStatus.value = `成功生成 ${data.question_count} 道试题`

    // 2️⃣ 获取题目列表
    try {
      const qRes = await exerciseService.getGeneratedQuestions(convId)
      console.log("📌 getGeneratedQuestions 返回:", qRes)
      generatedQuestions.value = qRes.questions || []
    } catch (err) {
      console.error('读取生成题目列表失败：', err)
      ElMessage.warning('题目已经生成，但在读取题目列表时出错')
    }

  } catch (error) {
    console.error('生成失败：', error)
    const msg =
      error.response?.data?.detail ||
      error.message ||
      '未知错误'
    ElMessage.error('生成试题失败，请稍后重试：' + msg)
    generationStatus.value = '生成失败'
  } finally {
    generating.value = false
  }
}'''

new_func = '''const startGeneration = async () => {
  if (samples.value.length === 0) {
    ElMessage.warning('请先上传样本试题')
    return
  }

  // 检查是否有已完成的样本
  const completedSamples = samples.value.filter(s => s.status === 'completed')
  if (completedSamples.length === 0) {
    const pendingSamples = samples.value.filter(s => s.status === 'pending')
    if (pendingSamples.length > 0) {
      ElMessage.warning(`有 ${pendingSamples.length} 个样本正在解析中，请稍等片刻`)
    } else {
      ElMessage.error('样本解析失败，请重新上传')
    }
    return
  }

  generating.value = true
  generationStatus.value = '正在清除旧缓存并启动生成任务...'
  generationResult.value = null
  generatedQuestions.value = []

  try {
    const convId = conversation_id.value || 'default'

    // 1️⃣ 调用"生成题目"（后端会自动清除旧缓存）
    const res = await api.post(
      `/api/conversations/${convId}/exercises/generate`
    )

    const data = res
    console.log("🔥 /generate 返回:", data)

    if (!data || typeof data.question_count === "undefined") {
      throw new Error("后端未返回 question_count")
    }

    generationResult.value = data
    generationStatus.value = `✅ 成功生成 ${data.question_count} 道全新试题`

    // 2️⃣ 获取题目列表
    try {
      const qRes = await exerciseService.getGeneratedQuestions(convId)
      console.log("📌 getGeneratedQuestions 返回:", qRes)
      generatedQuestions.value = qRes.questions || []
      ElMessage.success(`已生成 ${qRes.questions?.length || 0} 道新题目`)
    } catch (err) {
      console.error('读取生成题目列表失败：', err)
      ElMessage.warning('题目已经生成，但在读取题目列表时出错')
    }

  } catch (error) {
    console.error('生成失败：', error)
    const msg =
      error.response?.data?.detail ||
      error.message ||
      '未知错误'
    
    // 更友好的错误提示
    if (msg.includes('未找到任何样本试卷')) {
      ElMessage.error('当前会话未上传样本试卷，请先在上方上传PDF/DOCX/TXT文件')
    } else if (msg.includes('正在解析中')) {
      ElMessage.warning(msg)
    } else {
      ElMessage.error('生成试题失败：' + msg)
    }
    
    generationStatus.value = '❌ 生成失败'
  } finally {
    generating.value = false
  }
}'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ 已更新 ExerciseViewer.vue")
else:
    print("❌ 未找到要替换的函数")
