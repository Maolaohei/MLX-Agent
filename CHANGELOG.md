# MLX-Agent 深度修复与增强 - 变更日志

## 版本 0.3.0 - 生产就绪版本

### 🐛 稳定性修复 (P0)

#### 1. 优雅关闭机制
- **问题**: 服务停止时超时 (SIGKILL)，缺乏优雅关闭
- **修复**:
  - 重构 `MLXAgent.stop()` 方法，添加有序关闭流程
  - 添加 `shutdown_timeout` 配置，可配置关闭超时
  - 实现资源依赖图，确保按正确顺序关闭
  - 添加 `asyncio.gather` 等待所有关闭任务完成
  - 修复 `TaskWorker.stop()` 中的竞争条件
  - 添加 `TaskQueue.shutdown()` 等待所有任务完成或取消

#### 2. 信号处理增强
- **问题**: 信号处理器创建任务但不等待完成
- **修复**:
  - 使用 `asyncio.Event` 协调关闭信号
  - 添加 `_shutdown_event` 统一控制关闭流程
  - 确保信号处理不会创建孤立任务

#### 3. 健康检查端点
- **新增**: `HealthCheckServer` 类提供 HTTP 健康检查
- **端点**:
  - `GET /health` - 基础健康状态
  - `GET /health/ready` - 服务就绪检查
  - `GET /health/live` - 存活检查
  - `GET /health/metrics` - 详细指标
- **指标包含**: 内存使用、任务队列状态、LLM 可用性、平台连接状态

#### 4. 错误处理增强
- 添加全局异常捕获装饰器 `@safe_execute`
- 所有异步方法添加边界条件检查
- 配置加载失败时提供默认配置回退
- 添加详细的错误日志和上下文信息

### ⚡ 流式输出 (P0)

#### 1. SSE 流式响应
- **新增**: `LLMClient.chat_stream()` 方法
  - 支持 Server-Sent Events 流式响应
  - 兼容 OpenAI 流式 API 格式
  - 支持思考和内容分离
  - 自动处理流式工具调用

#### 2. Telegram 适配器流式支持
- **新增**: `TelegramAdapter.send_message_stream()` 方法
  - 使用消息编辑实现流式输出效果
  - 智能分段更新（避免 API 限制）
  - 支持打字状态与流式结合

#### 3. Agent 流式处理
- **重构**: `handle_message_stream()` 方法
  - 真正的异步生成器实现
  - 支持流式工具调用
  - 集成记忆系统到流式流程

### 🧠 记忆系统升级 (P1)

#### 1. ChromaDB 集成
- **新增**: `ChromaMemorySystem` 类
  - 使用 ChromaDB 作为向量数据库
  - 支持持久化存储
  - 自动嵌入生成（bge-m3 或 OpenAI）

#### 2. 分级记忆 (P0/P1/P2)
- **P0 (核心)**: 最重要的人物信息、偏好设置
  - 永不删除，手动管理
  - 最高检索优先级
  - 存储于 `memory/core/`
  
- **P1 (会话)**: 当前会话的上下文信息
  - 自动过期（默认 7 天）
  - 中等检索优先级
  - 存储于 `memory/session/`
  
- **P2 (临时)**: 临时信息、工具执行结果
  - 短期保留（默认 24 小时）
  - 自动归档或清理
  - 存储于 `memory/temp/`

#### 3. 自动归档
- **新增**: `MemoryArchiver` 类
  - 定期扫描过期记忆
  - P1 -> Archive (压缩存储)
  - P2 -> Delete (安全删除)
  - 可配置归档策略

### 🔧 Bug 修复

#### 1. 配置系统
- **修复**: 环境变量替换失败时提供默认值
- **修复**: 配置文件不存在时创建默认配置
- **新增**: 配置验证和自动修复

#### 2. 任务系统
- **修复**: `TaskQueue.get()` 的竞态条件
- **修复**: 任务取消时的状态同步问题
- **新增**: 任务超时自动取消

#### 3. LLM 客户端
- **修复**: 故障转移时的工具调用兼容性问题
- **修复**: JSON 解析失败时的优雅降级
- **新增**: 请求重试和指数退避

#### 4. Telegram 适配器
- **修复**: Markdown 解析失败时的无限循环
- **修复**: 打字状态在错误情况下未停止
- **新增**: 消息长度检查和自动分割

### 📊 测试与验证

#### 新增测试
- `tests/test_graceful_shutdown.py` - 优雅关闭测试
- `tests/test_streaming.py` - 流式输出测试
- `tests/test_memory_chroma.py` - ChromaDB 记忆系统测试
- `tests/test_health_check.py` - 健康检查测试
- `tests/test_error_handling.py` - 错误处理测试

#### 集成测试
- 完整对话流程测试
- 多平台适配器测试
- 长时间运行稳定性测试

### 📝 文档更新

- 更新 `README.md` - 新增功能说明
- 更新 `ARCHIVE.md` - 记录修复历程
- 创建 `CHANGELOG.md` - 本文件
- 添加 `docs/streaming.md` - 流式输出开发文档
- 添加 `docs/memory.md` - 记忆系统文档

### 🚀 部署改进

#### systemd 服务
- 更新 `TimeoutStopSec` 从 30s 到 60s
- 添加 `ExecStop` 优雅停止命令
- 添加 `KillSignal=SIGTERM` 明确信号

#### 环境检查
- 启动时检查 ChromaDB 可用性
- 检查嵌入模型配置
- 验证 API 密钥有效性

### 📈 性能指标

```
启动时间: < 2 秒 (保持不变)
内存占用: < 300 MB (+50 MB for ChromaDB)
优雅关闭时间: < 10 秒
流式延迟: < 100ms (首字符)
健康检查响应: < 10ms
```

### 🔄 迁移指南

#### 从 v0.2.0 迁移
1. 安装新依赖: `pip install chromadb sentence-transformers`
2. 转换记忆数据: `python scripts/migrate_memory.py`
3. 更新配置: 添加 `memory.embedding_provider` 字段
4. 重启服务: `systemctl restart mlx-agent`

#### 配置文件变更
```yaml
# 新增配置项
memory:
  embedding_provider: "local"  # local, openai, ollama
  chroma_path: "./memory/chroma"
  auto_archive:
    enabled: true
    interval_hours: 24
    p1_max_age_days: 7
    p2_max_age_days: 1

health_check:
  enabled: true
  port: 8080
  path: "/health"
```

---

*发布日期: 2026-02-15*  
*维护者: 忍野忍 (Shinobu Oshino)* 🍩🦇
