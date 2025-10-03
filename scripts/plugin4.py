"""
课堂对话服务（InClassChatSvc）
功能：提供课堂中实时 AI 问答，基于最近转录和阶段性总结回答问题
"""

import json
import os
import sqlite3
import time
import uuid
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import openai


@dataclass
class ChatContext:
    """聊天上下文数据结构"""
    recent_transcripts: List[str]
    partial_summaries: List[str]
    course_profile: Dict[str, Any]
    context_timestamp: datetime
    total_context_length: int


@dataclass
class ChatResponse:
    """AI回答数据结构"""
    question: str
    answer: str
    context_sources: List[str]  # 引用的上下文来源
    timestamp: datetime
    model_used: str
    confidence_score: float
    session_id: str


@dataclass
class APIRequest:
    """标准化API请求结构"""
    version: str
    request_id: str
    source: Dict[str, Any]
    intent: Dict[str, Any]
    expect: Dict[str, Any]


@dataclass
class APIResponse:
    """标准化API回复结构"""
    request_id: str
    result: Dict[str, Any]
    info: Dict[str, Any]


class InClassChatSvc:
    """课堂对话服务"""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        """
        初始化课堂对话服务
        
        Args:
            openai_api_key: OpenAI API密钥。如果为None，则从环境变量OPENAI_API_KEY中获取
            
        Raises:
            ValueError: 无法获取有效的API密钥时抛出
        """
        if openai_api_key is None:
            openai_api_key = os.getenv('OPENAI_API_KEY')
            
        if not openai_api_key:
            raise ValueError(
                "未找到OpenAI API密钥。请通过以下方式之一提供：\n"
                "1. 在初始化时传入 openai_api_key 参数\n"
                "2. 设置环境变量 OPENAI_API_KEY\n"
                "   Windows: $env:OPENAI_API_KEY='your_api_key'\n"
                "   Linux/Mac: export OPENAI_API_KEY='your_api_key'"
            )
            
        self.client = openai.OpenAI(api_key=openai_api_key)
        self.model_name = "gpt-4o-mini"  # 使用gpt-4o-mini代替gpt-5-nano（不存在）
        self.version = "1.0.0"
        
        # 配置参数
        self.max_context_length = 4000  # 最大上下文长度
        self.max_transcript_segments = 5  # 最多包含的转录片段数
        self.max_summary_segments = 3    # 最多包含的总结片段数
        
        # 数据库配置
        self.db_path = "summaries.db"
        self.transcript_table = "transcripts"  # 假设存在转录表
        self.summaries_table = "summaries"    # 总结表已存在
    
    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化API请求处理入口
        
        Args:
            request_data: 符合API规范的请求字典
            
        Returns:
            Dict[str, Any]: 符合API规范的响应字典
        """
        try:
            # 验证请求格式
            api_request = self._validate_request(request_data)
            
            # 处理业务逻辑
            result = self._process_intent(api_request)
            
            # 构建标准响应
            return self._build_response(api_request.request_id, result, 200, "处理成功")
            
        except ValueError as e:
            return self._build_error_response(
                request_data.get("request_id", str(uuid.uuid4())), 
                400, 
                f"请求参数错误: {str(e)}"
            )
        except Exception as e:
            return self._build_error_response(
                request_data.get("request_id", str(uuid.uuid4())), 
                500, 
                f"服务内部错误: {str(e)}"
            )
    
    def _validate_request(self, request_data: Dict[str, Any]) -> APIRequest:
        """验证API请求格式"""
        required_fields = ["version", "request_id", "source", "intent", "expect"]
        
        for field in required_fields:
            if field not in request_data:
                raise ValueError(f"缺少必需字段: {field}")
        
        # 验证版本兼容性
        if request_data["version"] != self.version:
            raise ValueError(f"版本不兼容: 期望 {self.version}, 收到 {request_data['version']}")
        
        return APIRequest(**request_data)
    
    def _process_intent(self, api_request: APIRequest) -> Dict[str, Any]:
        """处理具体的业务意图"""
        intent = api_request.intent
        action = intent.get("action")
        
        if action == "ask_question":
            # 课堂问答
            question = intent.get("question")
            recent_transcripts = intent.get("recent_transcripts", [])
            partial_summaries = intent.get("partial_summaries", [])
            course_profile = intent.get("course_profile", {})
            session_id = intent.get("session_id")
            
            if not question:
                raise ValueError("ask_question操作需要question参数")
            
            # 使用提供的数据构建上下文
            context = self._build_context_from_data(
                recent_transcripts, partial_summaries, course_profile
            )
            
            # 生成AI回答
            chat_response = self._generate_ai_response(question, context, session_id)
            
            # 根据intent字段格式化返回结果
            result = self._format_chat_result(chat_response, intent)
            
            return result
            
        else:
            raise ValueError(f"不支持的操作: {action}")
    
    def _build_context_from_data(self, 
                                recent_transcripts: List[str], 
                                partial_summaries: List[str], 
                                course_profile: Dict[str, Any]) -> ChatContext:
        """从提供的数据构建聊天上下文"""
        # 计算总上下文长度
        total_length = sum(len(t) for t in recent_transcripts) + \
                      sum(len(s) for s in partial_summaries) + \
                      len(json.dumps(course_profile, ensure_ascii=False))
        
        return ChatContext(
            recent_transcripts=recent_transcripts,
            partial_summaries=partial_summaries,
            course_profile=course_profile,
            context_timestamp=datetime.now(),
            total_context_length=total_length
        )
    
    def _generate_ai_response(self, question: str, context: ChatContext, session_id: str = None) -> ChatResponse:
        """生成AI回答"""
        if session_id is None:
            session_id = f"chat_{int(time.time())}"
        
        # 构建系统提示词
        system_prompt = self._build_system_prompt(context)
        
        # 构建用户提示词
        user_prompt = self._build_user_prompt(question, context)
        
        # 调用GPT API
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,  # 较低温度确保答案准确性
                max_tokens=500,
                top_p=0.9
            )
            
            answer = response.choices[0].message.content.strip()
            
            # 提取引用来源
            context_sources = self._extract_context_sources(answer, context)
            
            # 计算置信度分数
            confidence_score = self._calculate_confidence_score(question, answer, context)
            
            return ChatResponse(
                question=question,
                answer=answer,
                context_sources=context_sources,
                timestamp=datetime.now(),
                model_used=self.model_name,
                confidence_score=confidence_score,
                session_id=session_id
            )
            
        except Exception as e:
            raise Exception(f"AI问答服务调用失败: {str(e)}")
    
    def _format_chat_result(self, chat_response: ChatResponse, intent: Dict[str, Any]) -> Dict[str, Any]:
        """根据intent字段格式化聊天结果"""
        result = {
            "chat_response": {
                "question": chat_response.question,
                "answer": chat_response.answer,
                "session_id": chat_response.session_id,
                "timestamp": chat_response.timestamp.isoformat(),
                "confidence_score": chat_response.confidence_score,
                "context_sources": chat_response.context_sources
            }
        }
        
        # 添加元数据
        if intent.get("include_metadata", False):
            result["metadata"] = {
                "service_version": self.version,
                "model_used": chat_response.model_used,
                "response_generated_at": datetime.now().isoformat(),
                "answer_length": len(chat_response.answer),
                "sources_count": len(chat_response.context_sources)
            }
        
        # 添加调试信息
        if intent.get("include_debug", False):
            result["debug"] = {
                "question_length": len(chat_response.question),
                "confidence_breakdown": {
                    "base_score": 0.5,
                    "adjustments": "基于上下文质量和关键词匹配"
                },
                "context_summary": {
                    "transcripts_count": len([s for s in chat_response.context_sources if "转录" in s]),
                    "summaries_count": len([s for s in chat_response.context_sources if "总结" in s])
                }
            }
        
        return result
    
    def _build_response(self, request_id: str, result: Dict[str, Any], 
                       status_code: int, description: str) -> Dict[str, Any]:
        """构建标准API响应"""
        return {
            "request_id": request_id,
            "result": result,
            "info": {
                "status_code": status_code,
                "description": description
            }
        }
    
    def _build_error_response(self, request_id: str, status_code: int, 
                             description: str) -> Dict[str, Any]:
        """构建错误响应"""
        return {
            "request_id": request_id,
            "result": {},
            "info": {
                "status_code": status_code,
                "description": description
            }
        }
    
    def ask_question(self, 
                    question: str, 
                    session_id: str = None,
                    time_window_minutes: int = 30) -> ChatResponse:
        """
        处理用户问题并返回AI回答
        
        Args:
            question: 用户问题
            session_id: 会话ID，如果为None则自动生成
            time_window_minutes: 获取上下文的时间窗口（分钟）
            
        Returns:
            ChatResponse: AI回答对象
            
        Raises:
            ValueError: 问题为空或无效
            Exception: API调用失败
        """
        if not question or len(question.strip()) < 3:
            raise ValueError("问题不能为空且至少包含3个字符")
        
        if session_id is None:
            session_id = f"chat_{int(time.time())}"
        
        # 构建上下文
        context = self._build_context(time_window_minutes)
        
        # 验证上下文
        if not context.recent_transcripts and not context.partial_summaries:
            raise ValueError("没有可用的课堂上下文数据，请确保转录或总结服务正在运行")
        
        # 构建系统提示词
        system_prompt = self._build_system_prompt(context)
        
        # 构建用户提示词
        user_prompt = self._build_user_prompt(question, context)
        
        # 调用GPT API
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,  # 较低温度确保答案准确性
                max_tokens=500,
                top_p=0.9
            )
            
            answer = response.choices[0].message.content.strip()
            
            # 提取引用来源
            context_sources = self._extract_context_sources(answer, context)
            
            # 计算置信度分数（简化实现）
            confidence_score = self._calculate_confidence_score(question, answer, context)
            
            return ChatResponse(
                question=question,
                answer=answer,
                context_sources=context_sources,
                timestamp=datetime.now(),
                model_used=self.model_name,
                confidence_score=confidence_score,
                session_id=session_id
            )
            
        except Exception as e:
            raise Exception(f"AI问答服务调用失败: {str(e)}")
    
    def _build_context(self, time_window_minutes: int) -> ChatContext:
        """
        构建问答上下文
        
        Args:
            time_window_minutes: 时间窗口（分钟）
            
        Returns:
            ChatContext: 上下文对象
        """
        # 获取最近的转录片段
        recent_transcripts = self._get_recent_transcripts(time_window_minutes)
        
        # 获取最近的阶段性总结
        partial_summaries = self._get_recent_summaries(time_window_minutes)
        
        # 获取课程画像
        course_profile = self._load_course_profile()
        
        # 计算总上下文长度
        total_length = sum(len(t) for t in recent_transcripts) + \
                      sum(len(s) for s in partial_summaries) + \
                      len(json.dumps(course_profile, ensure_ascii=False))
        
        return ChatContext(
            recent_transcripts=recent_transcripts,
            partial_summaries=partial_summaries,
            course_profile=course_profile,
            context_timestamp=datetime.now(),
            total_context_length=total_length
        )
    
    def _get_recent_transcripts(self, time_window_minutes: int) -> List[str]:
        """
        获取最近的转录片段
        
        Args:
            time_window_minutes: 时间窗口（分钟）
            
        Returns:
            List[str]: 转录文本列表
        """
        transcripts = []
        
        try:
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 创建转录表（如果不存在）- 实际应用中应该由STT服务创建
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    text_content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 计算时间窗口
            cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
            
            # 查询最近的转录记录
            cursor.execute('''
                SELECT text_content FROM transcripts 
                WHERE timestamp >= ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (cutoff_time.isoformat(), self.max_transcript_segments))
            
            results = cursor.fetchall()
            transcripts = [row[0] for row in results]
            
            conn.close()
            
        except sqlite3.Error as e:
            print(f"获取转录数据时数据库错误: {e}")
            # 返回空列表，让服务继续使用其他上下文
        
        return transcripts
    
    def _get_recent_summaries(self, time_window_minutes: int) -> List[str]:
        """
        获取最近的阶段性总结
        
        Args:
            time_window_minutes: 时间窗口（分钟）
            
        Returns:
            List[str]: 总结文本列表（Markdown格式）
        """
        summaries = []
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 计算时间窗口
            cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
            
            # 查询最近的总结记录
            cursor.execute('''
                SELECT markdown_content FROM summaries 
                WHERE timestamp >= ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (cutoff_time.isoformat(), self.max_summary_segments))
            
            results = cursor.fetchall()
            summaries = [row[0] for row in results]
            
            conn.close()
            
        except sqlite3.Error as e:
            print(f"获取总结数据时数据库错误: {e}")
        
        return summaries
    
    def _load_course_profile(self) -> Dict[str, Any]:
        """
        加载课程画像
        
        Returns:
            Dict[str, Any]: 课程画像字典
        """
        try:
            course_profile_path = "course_profile.json"
            if os.path.exists(course_profile_path):
                with open(course_profile_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载课程画像失败: {e}")
        
        # 返回默认的空课程画像
        return {
            "main_title": "Unknown Course",
            "subtitle": "",
            "introduction": "",
            "keywords": [],
            "outline": [],
            "abbreviations": {},
            "formulas_symbols": [],
            "proper_nouns_cases": [],
            "learning_objectives": []
        }
    
    def _build_system_prompt(self, context: ChatContext) -> str:
        """
        构建系统提示词
        
        Args:
            context: 上下文对象
            
        Returns:
            str: 系统提示词
        """
        # 提取关键课程信息
        course_info = context.course_profile
        main_title = course_info.get('main_title', 'Unknown Course')
        keywords = ', '.join(course_info.get('keywords', [])[:20])
        objectives = '; '.join(course_info.get('learning_objectives', []))
        
        return f"""你是专业的课堂AI助手，负责回答关于"{main_title}"课程的实时问题。

课程信息：
- 标题：{main_title}
- 副标题：{course_info.get('subtitle', '')}
- 核心关键词：{keywords}
- 学习目标：{objectives}

回答要求：
1. 严格基于提供的课堂上下文回答，不得编造或添加课堂外知识
2. 如果上下文中没有相关信息，明确说明"根据当前课堂内容，我无法回答这个问题"
3. 回答要简洁准确，适合课堂环境
4. 在回答末尾引用具体的上下文来源，格式：[引用: 转录/总结]
5. 如果问题涉及公式或术语，优先使用课程画像中定义的内容
6. 保持专业性和学术性

上下文限制：
- 只能使用最近{len(context.recent_transcripts)}段转录和{len(context.partial_summaries)}段总结
- 总上下文长度：{context.total_context_length}字符"""
    
    def _build_user_prompt(self, question: str, context: ChatContext) -> str:
        """
        构建用户提示词
        
        Args:
            question: 用户问题
            context: 上下文对象
            
        Returns:
            str: 用户提示词
        """
        # 构建上下文信息
        context_parts = []
        
        # 添加课程画像
        context_parts.append("=== 课程画像 ===")
        context_parts.append(json.dumps(context.course_profile, ensure_ascii=False, indent=2))
        
        # 添加最近转录
        if context.recent_transcripts:
            context_parts.append("\n=== 最近转录内容 ===")
            for i, transcript in enumerate(context.recent_transcripts, 1):
                context_parts.append(f"转录片段 {i}:\n{transcript}")
        
        # 添加阶段性总结
        if context.partial_summaries:
            context_parts.append("\n=== 最近阶段性总结 ===")
            for i, summary in enumerate(context.partial_summaries, 1):
                context_parts.append(f"总结 {i}:\n{summary}")
        
        # 组合最终提示词
        full_context = "\n".join(context_parts)
        
        # 如果上下文过长，进行截断
        if len(full_context) > self.max_context_length:
            full_context = full_context[:self.max_context_length] + "... [上下文已截断]"
        
        return f"""请基于以下课堂上下文回答问题：

{full_context}

用户问题：{question}

请回答："""
    
    def _extract_context_sources(self, answer: str, context: ChatContext) -> List[str]:
        """
        提取答案中引用的上下文来源
        
        Args:
            answer: AI回答
            context: 上下文对象
            
        Returns:
            List[str]: 引用来源列表
        """
        sources = []
        
        # 检查是否引用了转录内容
        if context.recent_transcripts and any(
            keyword in answer.lower() for keyword in ["转录", "transcript", "刚才", "刚刚"]
        ):
            sources.append("最近转录内容")
        
        # 检查是否引用了总结内容
        if context.partial_summaries and any(
            keyword in answer.lower() for keyword in ["总结", "summary", "要点", "概念"]
        ):
            sources.append("阶段性总结")
        
        # 检查是否引用了课程画像
        course_keywords = context.course_profile.get('keywords', [])[:10]
        if any(keyword.lower() in answer.lower() for keyword in course_keywords):
            sources.append("课程画像")
        
        # 如果没有明确引用，标记为一般上下文
        if not sources:
            sources.append("课堂上下文")
        
        return sources
    
    def _calculate_confidence_score(self, question: str, answer: str, context: ChatContext) -> float:
        """
        计算回答的置信度分数（简化实现）
        
        Args:
            question: 用户问题
            answer: AI回答
            context: 上下文对象
            
        Returns:
            float: 置信度分数 (0.0-1.0)
        """
        score = 0.5  # 基础分数
        
        # 如果答案包含"无法回答"等词语，降低置信度
        if any(phrase in answer for phrase in ["无法回答", "不确定", "不清楚", "没有相关信息"]):
            score -= 0.3
        
        # 如果答案包含具体引用，提高置信度
        if "[引用:" in answer or "引用" in answer:
            score += 0.2
        
        # 如果上下文丰富，提高置信度
        if len(context.recent_transcripts) > 2 and len(context.partial_summaries) > 1:
            score += 0.2
        
        # 如果问题与课程关键词匹配，提高置信度
        course_keywords = [kw.lower() for kw in context.course_profile.get('keywords', [])]
        question_words = question.lower().split()
        if any(word in course_keywords for word in question_words):
            score += 0.1
        
        return max(0.0, min(1.0, score))  # 限制在0-1范围内
    
    def print_chat_response(self, response: ChatResponse) -> None:
        """打印聊天回答信息"""
        print("=== 课堂AI问答 ===")
        print(f"问题: {response.question}")
        print(f"回答: {response.answer}")
        print(f"引用来源: {', '.join(response.context_sources)}")
        print(f"置信度: {response.confidence_score:.2f}")
        print(f"时间: {response.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"模型: {response.model_used}")


def main():
    """主函数示例 - 演示标准化API请求体和回复体"""
    try:
        # 初始化服务
        chat_svc = InClassChatSvc()
        
        # 模拟输入数据
        sample_recent_transcripts = [
            "Today we're going to talk about coordinate systems in computer graphics. The most fundamental coordinate system we use is the Cartesian coordinate system, developed by René Descartes.",
            "In this system, we use x and y coordinates to represent points in 2D space. For 3D graphics, we add a z-axis.",
            "The conversion between different coordinate systems, such as from polar to Cartesian coordinates, uses the formulas x = r cos(α) and y = r sin(α)."
        ]
        
        sample_partial_summaries = [
            "## 📚 本段要点\n- 介绍了笛卡尔坐标系的基本概念\n- 说明了2D和3D坐标系的区别\n- 讲解了极坐标到笛卡尔坐标的转换\n\n## 🔑 关键概念\n- **笛卡尔坐标系**: 使用x, y, z轴表示点位置\n- **极坐标**: 使用r和α表示点位置\n- **坐标转换**: x = r cos(α), y = r sin(α)\n\n标签：#坐标系 #笛卡尔 #极坐标"
        ]
        
        sample_course_profile = {
            "main_title": "Introduction to Computer Graphics",
            "subtitle": "Module 1. Coordinate Systems",
            "keywords": ["coordinate systems", "Cartesian", "polar", "transformation", "graphics"],
            "learning_objectives": ["Understand coordinate systems", "Learn coordinate transformations"],
            "formulas_symbols": [
                {"symbol": "x", "description": "X坐标分量"},
                {"symbol": "y", "description": "Y坐标分量"},
                {"symbol": "r", "description": "极径"},
                {"symbol": "α", "description": "极角"}
            ]
        }
        
        # 测试请求1：基本问答
        request_data_1 = {
            "version": "1.0.0",
            "request_id": str(uuid.uuid4()),
            "source": {
                "timestamp": datetime.now().isoformat(),
                "page": "/class/123/chat",
                "app": {"name": "classguru-web", "version": "1.4.2"},
                "locale": "zh-CN",
                "timezone": "Asia/Shanghai"
            },
            "intent": {
                "action": "ask_question",
                "question": "什么是笛卡尔坐标系？它是如何工作的？",
                "recent_transcripts": sample_recent_transcripts,
                "partial_summaries": sample_partial_summaries,
                "course_profile": sample_course_profile,
                "session_id": "demo_chat_session"
            },
            "expect": {
                "include_metadata": True,
                "include_debug": True
            }
        }
        
        print("=== 请求体1 (课堂问答) ===")
        print(json.dumps(request_data_1, indent=2, ensure_ascii=False))
        
        response_1 = chat_svc.handle_request(request_data_1)
        
        print("\n=== 回复体1 ===")
        print(json.dumps(response_1, indent=2, ensure_ascii=False))
        
        # 测试请求2：复杂问题
        request_data_2 = {
            "version": "1.0.0",
            "request_id": str(uuid.uuid4()),
            "source": {
                "timestamp": datetime.now().isoformat(),
                "page": "/class/123/chat",
                "app": {"name": "classguru-web", "version": "1.4.2"},
                "locale": "zh-CN",
                "timezone": "Asia/Shanghai"
            },
            "intent": {
                "action": "ask_question",
                "question": "极坐标转换为笛卡尔坐标的公式是什么？能举个例子吗？",
                "recent_transcripts": sample_recent_transcripts,
                "partial_summaries": sample_partial_summaries,
                "course_profile": sample_course_profile
            },
            "expect": {
                "include_metadata": False,
                "include_debug": False
            }
        }
        
        print("\n=== 请求体2 (公式问答) ===")
        print(json.dumps(request_data_2, indent=2, ensure_ascii=False))
        
        response_2 = chat_svc.handle_request(request_data_2)
        
        print("\n=== 回复体2 ===")
        print(json.dumps(response_2, indent=2, ensure_ascii=False))
        
        print("\n� API使用方法：")
        print("1. 设置环境变量：$env:OPENAI_API_KEY='your_api_key'")
        print("2. 创建服务实例：chat_svc = InClassChatSvc()")
        print("3. 准备请求数据（包含question、recent_transcripts、partial_summaries、course_profile）")
        print("4. 发送API请求：response = chat_svc.handle_request(request_data)")
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")

if __name__ == "__main__":
    main()
