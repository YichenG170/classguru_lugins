import os
import json
import uuid
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from openai import OpenAI


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


@dataclass
class PostClassChatResponse:
    """课后问答响应数据结构"""
    question: str
    answer: str
    timestamp: datetime
    model_used: str
    session_id: str
    answer_length: int
    context_used: bool


class PostClassChatSvc:
    def __init__(self):
        # 获取 OpenAI API Key
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        self.client = OpenAI(api_key=self.openai_api_key)
        self.version = "1.0.0"
    
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
            # 课后问答
            user_question = intent.get("user_question")
            final_report_md = intent.get("final_report_md")
            session_id = intent.get("session_id")
            
            if not user_question:
                raise ValueError("ask_question操作需要user_question参数")
            if not final_report_md:
                raise ValueError("ask_question操作需要final_report_md参数")
            
            # 生成问答回复
            chat_response = self._generate_answer(user_question, final_report_md, session_id)
            
            # 根据expect字段格式化返回结果
            expect = api_request.expect
            result = self._format_chat_result(chat_response, expect)
            
            return result
            
        else:
            raise ValueError(f"不支持的操作: {action}")
    
    def _generate_answer(self, user_question: str, final_report_md: str, session_id: str = None) -> PostClassChatResponse:
        """生成问答回复"""
        if session_id is None:
            session_id = f"post_chat_{int(datetime.now().timestamp())}"
        
        # 调用原有的问答逻辑
        answer = self.answer_question(user_question, final_report_md)
        
        return PostClassChatResponse(
            question=user_question,
            answer=answer,
            timestamp=datetime.now(),
            model_used="gpt-4o-mini",
            session_id=session_id,
            answer_length=len(answer),
            context_used=bool(final_report_md)
        )
    
    def _format_chat_result(self, chat_response: PostClassChatResponse, expect: Dict[str, Any]) -> Dict[str, Any]:
        """根据expect字段格式化问答结果"""
        result = {
            "post_class_chat": {
                "question": chat_response.question,
                "answer": chat_response.answer,
                "session_id": chat_response.session_id,
                "timestamp": chat_response.timestamp.isoformat(),
                "answer_length": chat_response.answer_length
            }
        }
        
        # 添加元数据
        if expect.get("include_metadata", False):
            result["metadata"] = {
                "service_version": self.version,
                "model_used": chat_response.model_used,
                "response_generated_at": datetime.now().isoformat(),
                "context_used": chat_response.context_used,
                "question_length": len(chat_response.question)
            }
        
        # 添加分析信息
        if expect.get("include_analysis", False):
            result["analysis"] = {
                "question_type": self._analyze_question_type(chat_response.question),
                "answer_confidence": self._estimate_answer_confidence(chat_response.answer),
                "context_relevance": "high" if "报告" in chat_response.answer else "medium",
                "response_completeness": "complete" if len(chat_response.answer) > 100 else "brief"
            }
        
        return result
    
    def _analyze_question_type(self, question: str) -> str:
        """分析问题类型"""
        question_lower = question.lower()
        
        if any(word in question_lower for word in ["什么", "是什么", "what", "定义"]):
            return "definition"
        elif any(word in question_lower for word in ["如何", "怎么", "how", "方法"]):
            return "how_to"
        elif any(word in question_lower for word in ["为什么", "原因", "why"]):
            return "why"
        elif any(word in question_lower for word in ["例子", "举例", "example"]):
            return "example"
        elif "?" in question or "？" in question:
            return "question"
        else:
            return "general"
    
    def _estimate_answer_confidence(self, answer: str) -> str:
        """估计回答置信度"""
        if any(phrase in answer for phrase in ["不确定", "可能", "大概", "也许"]):
            return "low"
        elif any(phrase in answer for phrase in ["根据报告", "明确", "确定"]):
            return "high"
        else:
            return "medium"
    
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

    def answer_question(self, user_question: str, final_report_md: str) -> str:
        """
        基于最终总结报告提供问答。

        :param user_question: 用户问题 (str)
        :param final_report_md: 最终总结报告 (Markdown str)
        :return: AI 回答 (str)
        """

        prompt = f"""
        你是一个教育问答助手。请基于以下最终总结报告回答用户的问题。回答必须严格基于报告内容，不能偏离报告范围或添加虚构信息。保持回答的整体性和总结性，提供全局视角的总结。

        最终总结报告（上下文）：
        {final_report_md}

        用户问题：
        {user_question}

        输出：
        - 直接给出回答，带全局性总结。
        - 如果问题超出报告范围，礼貌说明并建议参考报告。
        - 使用清晰、简洁的语言。
        """

        # 调用 OpenAI API，使用 gpt-4o-mini
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant specialized in educational Q&A based on provided reports."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1024
        )

        # 提取生成的回答
        answer = response.choices[0].message.content.strip()
        return answer

if __name__ == "__main__":
    """主函数示例 - 演示标准化API请求体和回复体"""
    try:
        # 初始化服务
        chat_svc = PostClassChatSvc()
        
        # 模拟最终总结报告数据
        sample_final_report = """
# 课后总结报告

## 1. 关键知识点
- 坐标系统：笛卡尔坐标系和极坐标系
- 坐标转换：极坐标到笛卡尔坐标的数学公式
- 三角函数：sin、cos在坐标转换中的应用
- 计算机图形学：坐标系统在渲染中的重要性

## 2. 每个知识点的细节

### 坐标系统
- **笛卡尔坐标系**：由René Descartes开发，使用x、y坐标表示2D空间中的点
- **极坐标系**：使用半径r和角度α表示点的位置
- **3D扩展**：笛卡尔坐标系可扩展到3D，添加z轴

### 坐标转换公式
- **极坐标到笛卡尔坐标**：
  - x = r cos(α)
  - y = r sin(α)
- **应用场景**：计算机图形学中对象的坐标变换

### 实际应用
- 计算机图形学中需要在不同坐标系间转换对象
- 渲染过程中的坐标变换是基础操作

## 3. 重要概念总结
- 坐标系统是计算机图形学的基础
- 不同坐标系各有优势，需要根据场景选择
- 数学公式是实现坐标转换的关键工具
        """
        
        # 测试请求1：基本问答
        request_data_1 = {
            "version": "1.0.0",
            "request_id": str(uuid.uuid4()),
            "source": {
                "timestamp": datetime.now().isoformat(),
                "page": "/class/123/post-chat",
                "app": {"name": "classguru-web", "version": "1.4.2"},
                "locale": "zh-CN",
                "timezone": "Asia/Shanghai"
            },
            "intent": {
                "action": "ask_question",
                "user_question": "什么是极坐标系？它与笛卡尔坐标系有什么区别？",
                "final_report_md": sample_final_report,
                "session_id": "demo_post_chat_session"
            },
            "expect": {
                "include_metadata": True,
                "include_analysis": True
            }
        }
        
        print("=== 请求体1 (课后问答) ===")
        print(json.dumps(request_data_1, indent=2, ensure_ascii=False))
        
        response_1 = chat_svc.handle_request(request_data_1)
        
        print("\n=== 回复体1 ===")
        print(json.dumps(response_1, indent=2, ensure_ascii=False))
        
        # 测试请求2：公式相关问题
        request_data_2 = {
            "version": "1.0.0",
            "request_id": str(uuid.uuid4()),
            "source": {
                "timestamp": datetime.now().isoformat(),
                "page": "/class/123/post-chat",
                "app": {"name": "classguru-web", "version": "1.4.2"},
                "locale": "zh-CN",
                "timezone": "Asia/Shanghai"
            },
            "intent": {
                "action": "ask_question",
                "user_question": "极坐标转换为笛卡尔坐标的公式是什么？请解释一下。",
                "final_report_md": sample_final_report
            },
            "expect": {
                "include_metadata": False,
                "include_analysis": True
            }
        }
        
        print("\n=== 请求体2 (公式问答) ===")
        print(json.dumps(request_data_2, indent=2, ensure_ascii=False))
        
        response_2 = chat_svc.handle_request(request_data_2)
        
        print("\n=== 回复体2 ===")
        print(json.dumps(response_2, indent=2, ensure_ascii=False))
        
        print("\n📋 API使用方法：")
        print("1. 设置环境变量：$env:OPENAI_API_KEY='your_api_key'")
        print("2. 创建服务实例：chat_svc = PostClassChatSvc()")
        print("3. 准备请求数据（包含user_question和final_report_md）")
        print("4. 发送API请求：response = chat_svc.handle_request(request_data)")
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")


def demo_api_usage():
    """API使用示例"""
    request_example = {
        "version": "1.0.0",
        "request_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
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
            "final_report_md": "# 最终总结报告\n\n## 关键知识点\n- 知识点1\n- 知识点2\n\n## 详细内容\n...",
            "session_id": "可选的会话ID"
        },
        "expect": {
            "include_metadata": True,
            "include_analysis": True
        }
    }
    
    print("=== API请求示例模板 ===")
    print(json.dumps(request_example, indent=2, ensure_ascii=False))