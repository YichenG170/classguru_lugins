# ClassGuru智能课堂插件系统

一个基于OpenAI的智能课堂服务插件集合，提供从文档分析、实时转录、阶段性总结、课堂问答到最终报告生成的完整教学支持流程。

## 🚀 项目概述

ClassGuru插件系统包含6个核心服务插件，每个插件都采用标准化的API请求体/回复体格式，确保系统的一致性和可扩展性。

### 📁 项目结构

```
ClassGuru/
├── scripts/
│   ├── plugin1.py          # 文档分析服务 (MaterialSvc)
│   ├── plugin2.py          # 实时转录服务 (STTService)
│   ├── plugin3.py          # 阶段性总结服务 (PartialSummSvc)
│   ├── plugin4.py          # 课堂对话服务 (InClassChatSvc)
│   ├── plugin5.py          # 最终报告服务 (FinalReportSvc)
│   └── plugin6.py          # 课后问答服务 (PostClassChatSvc)
├── plugin_env/             # Python虚拟环境
├── requirements.txt       # 依赖包列表
└── README.md             # 项目文档
```

## 🔧 环境设置

### Python 虚拟环境

本项目使用 Python 3.12 虚拟环境来管理依赖包。

#### 1. 创建虚拟环境

```powershell
python -m venv plugin_env
```

#### 2. 激活虚拟环境

```powershell
.\plugin_env\Scripts\Activate.ps1
```

激活成功后，命令提示符前会显示 `(plugin_env)` 标识。

#### 3. 安装依赖

```powershell
pip install -r requirements.txt
```

#### 4. 停用虚拟环境

```powershell
deactivate
```

### 环境变量配置

设置OpenAI API密钥：

```powershell
$env:OPENAI_API_KEY='your_openai_api_key_here'
```

## 📚 插件详细说明

### Plugin1: 文档分析服务 (MaterialSvc)

**功能**: 处理用户上传的文档（PPT、PDF、图片、笔记），生成课程画像（CourseProfile JSON）

**支持格式**: PDF, PPT, PPTX, JPG, JPEG, PNG, TXT, MD

**API请求体**:
```json
{
  "version": "1.0.0",
  "request_id": "unique_request_id",
  "source": {
    "timestamp": "2025-10-04T12:00:00Z",
    "page": "/class/123/material",
    "app": {"name": "classguru-web", "version": "1.4.2"},
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  },
  "intent": {
    "action": "analyze",
    "file_path": "/path/to/document.pdf",
    "format": "full",
    "include_metadata": true
  },
  "expect": null
}
```

**API返回体**:
```json
{
  "request_id": "unique_request_id",
  "result": {
    "main_title": "课程主标题",
    "subtitle": "课程副标题",
    "introduction": "课程简介",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "outline": ["主题1", "主题2", "主题3"],
    "abbreviations": {
      "AI": "Artificial Intelligence",
      "ML": "Machine Learning"
    },
    "formulas_symbols": [
      {
        "symbol": "x",
        "description": "X坐标分量"
      }
    ],
    "proper_nouns_cases": ["专有名词1", "案例1"],
    "learning_objectives": ["学习目标1", "学习目标2"],
    "openai_file_id": "file-xxxxxxxxxxxxx",
    "metadata": {
      "generated_at": "2025-10-04T12:00:00Z",
      "service_version": "1.0.0",
      "total_keywords": 45,
      "total_outline_items": 10
    }
  },
  "info": {
    "status_code": 200,
    "description": "处理成功"
  }
}
```

**使用方法**:
```python
from scripts.plugin1 import MaterialSvc

# 初始化服务
material_svc = MaterialSvc()

# 发送API请求
response = material_svc.handle_request(request_data)
print(response)
```

### Plugin2: 实时转录服务 (STTService)

**功能**: 处理课堂实时语音流，实现实时转录和可选翻译

**特性**: WebSocket实时音频流处理、抖动缓冲区、自动翻译、多用户会话管理

**架构增强**: 
- ✅ **多连接支持**: 支持最多50个并发WebSocket连接
- ✅ **会话隔离**: 每个连接拥有独立的音频缓冲区和状态
- ✅ **连接管理**: 自动管理连接生命周期和资源清理
- ✅ **独立配置**: 每个会话可以有不同的语言和翻译设置

#### 🔄 连接流程

**1. 客户端连接初始化**
```javascript
// 前端连接示例
const ws = new WebSocket('ws://localhost:8765');

ws.onopen = function() {
    // 必须先发送初始化消息
    ws.send(JSON.stringify({
        type: 'init',
        session_id: 'class_123_student_1',  // 可选，不提供会自动生成
        language: 'en',                     // 音频语言
        translate_to: 'zh',                 // 翻译目标语言（可选）
        display_subtitles: true             // 是否显示字幕
    }));
};

// 接收初始化确认
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    if (data.type === 'init_response') {
        console.log('连接成功:', {
            session_id: data.session_id,
            connection_id: data.connection_id,
            server_version: data.server_version
        });
        
        // 现在可以发送音频数据
        startAudioStreaming();
    }
};
```

**2. 音频数据发送**
```javascript
function sendAudioData(audioBlob) {
    // 直接发送二进制音频数据
    ws.send(audioBlob);
}

// 接收转录结果
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    switch(data.type) {
        case 'ack':
            // 音频帧确认
            console.log(`帧 ${data.sequence} 已确认`);
            break;
            
        case 'transcription':
            // 转录结果
            console.log('转录:', data.original_text);
            if (data.translated_text) {
                console.log('翻译:', data.translated_text);
            }
            break;
            
        case 'error':
            console.error('错误:', data.message);
            break;
    }
};
```

**3. 控制消息**
```javascript
// 启用/禁用翻译
ws.send(JSON.stringify({
    type: 'enable_translation',
    enabled: true,
    target_lang: 'zh'
}));

// 控制字幕显示
ws.send(JSON.stringify({
    type: 'start_display'  // 或 'stop_display'
}));

// 心跳检测
ws.send(JSON.stringify({
    type: 'ping'
}));
```

#### 🏗️ 会话管理架构

**连接管理器 (ConnectionManager)**
- 管理最多50个并发连接
- 每个连接分配唯一的connection_id
- 自动清理断开的连接资源

**用户会话 (UserSession)**
- 每个会话拥有独立的：
  - JitterBuffer（抖动缓冲区）
  - AudioQueue（音频队列）
  - 语言设置和翻译配置
  - 统计信息和状态

**资源隔离**
```python
# 每个会话的独立资源
UserSession {
    session_id: "class_123_student_1"
    connection_id: "uuid-12345"
    jitter_buffer: JitterBuffer()      # 独立缓冲区
    audio_queue: Queue(maxsize=1000)   # 独立队列
    language: "en"                     # 独立语言设置
    translate_to: "zh"                 # 独立翻译设置
    display_subtitles: true            # 独立显示设置
    stats: ConnectionStats()           # 独立统计
}
```

#### 🚀 启动多连接服务

**服务器启动**
```python
from scripts.plugin2 import STTService
import asyncio

# 初始化服务（支持最多50个连接）
stt_service = STTService(max_connections=50)

# 启动WebSocket服务器
async def start_service():
    await stt_service.start_websocket_server(host="localhost", port=8765)
    print("多连接STT服务器已启动")
    
    # 保持服务运行
    await asyncio.Future()

asyncio.run(start_service())
```

#### 🧪 测试多连接

**运行测试脚本**
```powershell
# 1. 启动Plugin2服务器
python scripts/plugin2.py

# 2. 在另一个终端运行测试
python test_multi_client.py
```

**测试内容**
- ✅ 单客户端连接和音频发送
- ✅ 5个客户端并发连接
- ✅ 会话隔离验证（不同配置）
- ✅ 连接断开和资源清理

#### 📊 性能指标

**并发能力**
- 最大连接数：50个并发WebSocket连接
- 每连接音频队列：1000帧缓冲
- 每连接独立的OpenAI API调用

**资源管理**
- 自动连接超时：30秒初始化超时
- 心跳检测：支持ping/pong机制
- 资源清理：连接断开时自动清理所有相关资源

**API请求体**:
```json
{
  "version": "1.0.0",
  "request_id": "unique_request_id",
  "source": {
    "timestamp": "2025-10-04T12:00:00Z",
    "page": "/class/123/transcribe",
    "app": {"name": "classguru-web", "version": "1.4.2"},
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  },
  "intent": {
    "action": "transcribe_audio",
    "audio_data": "base64_encoded_audio",
    "language": "en",
    "translate_to": "zh",
    "include_translation": true,
    "include_confidence": true
  },
  "expect": null
}
```

**API返回体**:
```json
{
  "request_id": "unique_request_id",
  "result": {
    "timestamp": "2025-10-04T12:00:00Z",
    "subtitle": {
      "original": "原始转录文本",
      "translated": "翻译后文本"
    },
    "language": "en",
    "confidence": 0.95,
    "metadata": {
      "service_version": "1.0.0",
      "processed_at": "2025-10-04T12:00:00Z",
      "audio_duration": 2.5,
      "translation_enabled": true,
      "target_language": "zh"
    },
    "technical_details": {
      "audio_config": {
        "sample_rate": 16000,
        "channels": 1,
        "encoding": "opus"
      },
      "model_used": "whisper-1",
      "processing_time": 0.8
    }
  },
  "info": {
    "status_code": 200,
    "description": "处理成功"
  }
}
```

**使用方法**:
```python
from scripts.plugin2 import STTService
import asyncio

# 初始化服务
stt_service = STTService()

# WebSocket服务器
async def start_service():
    await stt_service.start_websocket_server(host="localhost", port=8765)

# 运行服务
asyncio.run(start_service())
```

### Plugin3: 阶段性总结服务 (PartialSummSvc)

**功能**: 基于转录文本和CourseProfile，使用gpt-4o-mini生成简洁的Markdown格式阶段性总结

**API请求体**:
```json
{
  "version": "1.0.0",
  "request_id": "unique_request_id",
  "source": {
    "timestamp": "2025-10-04T12:00:00Z",
    "page": "/class/123/summary",
    "app": {"name": "classguru-web", "version": "1.4.2"},
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  },
  "intent": {
    "action": "generate_summary",
    "course_profile": {
      "main_title": "课程标题",
      "keywords": ["关键词1", "关键词2"],
      "learning_objectives": ["目标1", "目标2"]
    },
    "transcript_text": "转录文本内容...",
    "session_id": "session_123",
    "include_metadata": true,
    "include_statistics": true
  },
  "expect": null
}
```

**API返回体**:
```json
{
  "request_id": "unique_request_id",
  "result": {
    "summary": {
      "session_id": "session_123",
      "timestamp": "2025-10-04T12:00:00Z",
      "markdown_content": "## 📚 本段要点\n- 要点1\n- 要点2\n\n## 🔑 关键概念\n- **概念1**: 说明\n- **概念2**: 说明\n\n## 💡 重要提醒\n- 注意事项\n\n标签：#概念1 #概念2",
      "word_count": 156,
      "course_tags": ["概念1", "概念2", "重点"]
    },
    "metadata": {
      "service_version": "1.0.0",
      "generated_at": "2025-10-04T12:00:00Z",
      "model_used": "gpt-4o-mini",
      "content_length": 280,
      "tag_count": 3
    },
    "statistics": {
      "markdown_sections": 3,
      "key_concepts_count": 2,
      "important_points_count": 2,
      "reminders_count": 1
    }
  },
  "info": {
    "status_code": 200,
    "description": "处理成功"
  }
}
```

**使用方法**:
```python
from scripts.plugin3 import PartialSummSvc

# 初始化服务
partial_summ_svc = PartialSummSvc()

# 发送API请求
response = partial_summ_svc.handle_request(request_data)
print(response)
```

### Plugin4: 课堂对话服务 (InClassChatSvc)

**功能**: 提供课堂中实时AI问答，基于最近转录和阶段性总结回答问题

**API请求体**:
```json
{
  "version": "1.0.0",
  "request_id": "unique_request_id",
  "source": {
    "timestamp": "2025-10-04T12:00:00Z",
    "page": "/class/123/chat",
    "app": {"name": "classguru-web", "version": "1.4.2"},
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  },
  "intent": {
    "action": "ask_question",
    "question": "用户的问题文本",
    "recent_transcripts": [
      "最新的转录片段1",
      "最新的转录片段2"
    ],
    "partial_summaries": [
      "## 📚 本段要点\n- 要点1\n- 要点2"
    ],
    "course_profile": {
      "main_title": "课程标题",
      "keywords": ["关键词1", "关键词2"]
    },
    "session_id": "可选的会话ID",
    "include_metadata": true,
    "include_debug": false
  },
  "expect": null
}
```

**API返回体**:
```json
{
  "request_id": "unique_request_id",
  "result": {
    "chat_response": {
      "question": "用户的问题文本",
      "answer": "基于课堂上下文的AI回答",
      "session_id": "session_123",
      "timestamp": "2025-10-04T12:00:00Z",
      "confidence_score": 0.85,
      "context_sources": ["最近转录内容", "阶段性总结"]
    },
    "metadata": {
      "service_version": "1.0.0",
      "model_used": "gpt-4o-mini",
      "response_generated_at": "2025-10-04T12:00:00Z",
      "answer_length": 128,
      "sources_count": 2
    },
    "debug": {
      "question_length": 15,
      "confidence_breakdown": {
        "base_score": 0.5,
        "adjustments": "基于上下文质量和关键词匹配"
      },
      "context_summary": {
        "transcripts_count": 1,
        "summaries_count": 1
      }
    }
  },
  "info": {
    "status_code": 200,
    "description": "处理成功"
  }
}
```

**使用方法**:
```python
from scripts.plugin4 import InClassChatSvc

# 初始化服务
chat_svc = InClassChatSvc()

# 发送API请求
response = chat_svc.handle_request(request_data)
print(response)
```

### Plugin5: 最终报告服务 (FinalReportSvc)

**功能**: 生成三层次的课后总结报告，整合所有课堂数据

**API请求体**:
```json
{
  "version": "1.0.0",
  "request_id": "unique_request_id",
  "source": {
    "timestamp": "2025-10-04T12:00:00Z",
    "page": "/class/123/final-report",
    "app": {"name": "classguru-web", "version": "1.4.2"},
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  },
  "intent": {
    "action": "generate_final_report",
    "transcript_text": "全部转录文本...",
    "summaries_markdown": "# 总结1\n## 要点\n...",
    "user_dialog_text": "用户对话记录...",
    "course_profile_json": "{\"main_title\": \"课程\", ...}",
    "session_id": "session_123",
    "include_metadata": true,
    "include_source_summary": true,
    "include_statistics": true
  },
  "expect": null
}
```

**API返回体**:
```json
{
  "request_id": "unique_request_id",
  "result": {
    "final_report": {
      "report_id": "report_uuid_12345",
      "session_id": "session_123",
      "generated_at": "2025-10-04T12:00:00Z",
      "markdown_content": "# 课后总结报告\n\n## 1. 关键知识点\n- 知识点1\n- 知识点2\n\n## 2. 每个知识点的细节\n### 知识点1\n- 细节1\n- 细节2\n\n## 3. 对细节的扩展说明/解释\n### 知识点1 - 细节1\n- 扩展解释1\n- 扩展解释2",
      "word_count": 450,
      "section_count": 5
    },
    "metadata": {
      "service_version": "1.0.0",
      "model_used": "gpt-4o-mini",
      "generation_timestamp": "2025-10-04T12:00:00Z",
      "content_length": 1200,
      "processing_summary": "Three-tier structured final report generated"
    },
    "source_summary": {
      "transcript_length": 5000,
      "summaries_length": 800,
      "dialog_length": 300,
      "course_title": "Introduction to Computer Graphics",
      "keywords_count": 25,
      "objectives_count": 3
    },
    "statistics": {
      "content_breakdown": {
        "level_1_items": 3,
        "level_2_items": 2,
        "level_3_items": 1
      },
      "formatting_elements": {
        "bold_items": 8,
        "bullet_points": 12,
        "numbered_lists": 6
      }
    }
  },
  "info": {
    "status_code": 200,
    "description": "处理成功"
  }
}
```

**使用方法**:
```python
from scripts.plugin5 import FinalReportSvc

# 初始化服务
final_report_svc = FinalReportSvc()

# 发送API请求
response = final_report_svc.handle_request(request_data)
print(response)
```

### Plugin6: 课后问答服务 (PostClassChatSvc)

**功能**: 基于最终总结报告提供课后问答服务

**API请求体**:
```json
{
  "version": "1.0.0",
  "request_id": "unique_request_id",
  "source": {
    "timestamp": "2025-10-04T12:00:00Z",
    "page": "/class/123/post-chat",
    "app": {"name": "classguru-web", "version": "1.4.2"},
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  },
  "intent": {
    "action": "ask_question",
    "user_question": "用户的问题文本",
    "final_report_md": "# 最终总结报告\n\n## 关键知识点\n...",
    "session_id": "可选的会话ID",
    "include_metadata": true,
    "include_analysis": true
  },
  "expect": null
}
```

**API返回体**:
```json
{
  "request_id": "unique_request_id",
  "result": {
    "post_class_chat": {
      "question": "用户的问题文本",
      "answer": "基于最终报告的AI回答",
      "session_id": "session_123",
      "timestamp": "2025-10-04T12:00:00Z",
      "answer_length": 256
    },
    "metadata": {
      "service_version": "1.0.0",
      "model_used": "gpt-4o-mini",
      "response_generated_at": "2025-10-04T12:00:00Z",
      "context_used": true,
      "question_length": 20
    },
    "analysis": {
      "question_type": "definition",
      "answer_confidence": "high",
      "context_relevance": "high",
      "response_completeness": "complete"
    }
  },
  "info": {
    "status_code": 200,
    "description": "处理成功"
  }
}
```

**使用方法**:
```python
from scripts.plugin6 import PostClassChatSvc

# 初始化服务
post_chat_svc = PostClassChatSvc()

# 发送API请求
response = post_chat_svc.handle_request(request_data)
print(response)
```

## 🔄 完整工作流程

1. **文档上传** → Plugin1 分析生成课程画像
2. **课堂开始** → Plugin2 实时转录语音
3. **阶段总结** → Plugin3 生成阶段性总结
4. **课堂问答** → Plugin4 基于上下文回答问题
5. **课程结束** → Plugin5 生成最终报告
6. **课后复习** → Plugin6 基于报告提供问答

## 🗄️ 数据管理

### 无状态服务设计

为了提高系统的可扩展性和简化部署，所有插件都采用无状态设计：

- **Plugin3 (阶段性总结服务)**: 不再保存总结历史，直接返回生成的总结结果
- **Plugin4 (课堂对话服务)**: 通过API参数接收上下文数据（转录、总结、课程画像）
- **数据持久化**: 由调用方负责管理数据的存储和历史记录

### 优势

1. **简化部署**: 无需配置数据库文件
2. **水平扩展**: 支持多实例并发运行
3. **状态隔离**: 避免服务间的数据冲突
4. **灵活性**: 调用方可以选择任何存储方案

## 🚨 注意事项

1. **API密钥安全**: 确保OpenAI API密钥安全存储，不要硬编码在代码中
2. **文件权限**: 确保有读写权限访问文件系统
3. **网络连接**: Plugin2的WebSocket服务需要稳定的网络连接
4. **内存管理**: 处理大型文档时注意内存使用
5. **错误处理**: 每个插件都有完整的错误处理机制
6. **数据管理**: 调用方需要自行管理数据的持久化和历史记录

## 🔍 调试和测试

每个插件都包含main函数用于测试：

```powershell
# 测试单个插件
python scripts/plugin1.py
python scripts/plugin2.py
python scripts/plugin3.py
python scripts/plugin4.py
python scripts/plugin5.py
python scripts/plugin6.py
```

## 🤝 贡献

欢迎提交Issue和Pull Request来改进项目！

---

**ClassGuru智能课堂插件系统** - 让AI赋能教育，让学习更智能！