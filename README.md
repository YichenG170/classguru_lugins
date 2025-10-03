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
    "file_path": "/path/to/document.pdf"
  },
  "expect": {
    "format": "full",
    "include_metadata": true
  }
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

**特性**: WebSocket实时音频流处理、抖动缓冲区、自动翻译

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
    "translate_to": "zh"
  },
  "expect": {
    "include_translation": true,
    "include_confidence": true
  }
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
    "session_id": "session_123"
  },
  "expect": {
    "include_metadata": true,
    "include_statistics": true
  }
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
    "session_id": "可选的会话ID"
  },
  "expect": {
    "include_metadata": true,
    "include_debug": false
  }
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
    "session_id": "session_123"
  },
  "expect": {
    "include_metadata": true,
    "include_source_summary": true,
    "include_statistics": true
  }
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
    "session_id": "可选的会话ID"
  },
  "expect": {
    "include_metadata": true,
    "include_analysis": true
  }
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

### SQLite数据库表结构

#### summaries表（阶段性总结）
```sql
CREATE TABLE summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    markdown_content TEXT NOT NULL,
    course_tags TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### transcripts表（转录记录）
```sql
CREATE TABLE transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    text_content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 🚨 注意事项

1. **API密钥安全**: 确保OpenAI API密钥安全存储，不要硬编码在代码中
2. **文件权限**: 确保有读写权限访问数据库和文件
3. **网络连接**: Plugin2的WebSocket服务需要稳定的网络连接
4. **内存管理**: 处理大型文档时注意内存使用
5. **错误处理**: 每个插件都有完整的错误处理机制

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