"""
阶段性总结服务（PartialSummSvc）
功能：基于转录文本和CourseProfile，使用gpt-4o-mini生成简洁的Markdown格式阶段性总结
"""


import json
import os
import sqlite3
import time
import re
import uuid
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import openai


@dataclass
class PartialSummary:
    """阶段性总结数据结构"""
    session_id: str
    timestamp: datetime
    markdown_content: str
    course_tags: List[str]
    word_count: int


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


class PartialSummSvc:
    """阶段性总结服务"""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        """
        初始化阶段性总结服务
        
        Args:
            openai_api_key: OpenAI API密钥。如果为None，则从环境变量OPENAI_API_KEY中获取
        """
        if openai_api_key is None:
            openai_api_key = os.getenv('OPENAI_API_KEY')
            
        if not openai_api_key:
            raise ValueError(
                "未找到OpenAI API密钥。请通过以下方式之一提供：\n"
                "1. 在初始化时传入 openai_api_key 参数\n"
                "2. 设置环境变量 OPENAI_API_KEY"
            )
            
        self.client = openai.OpenAI(api_key=openai_api_key)
        self.model_name = "gpt-4o-mini"
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
        
        if action == "generate_summary":
            # 生成阶段性总结
            course_profile = intent.get("course_profile")
            transcript_text = intent.get("transcript_text")
            session_id = intent.get("session_id")
            
            if not course_profile:
                raise ValueError("generate_summary操作需要course_profile参数")
            if not transcript_text:
                raise ValueError("generate_summary操作需要transcript_text参数")
            
            # 生成总结
            summary = self.generate_summary(course_profile, transcript_text, session_id)
            
            # 根据intent字段格式化返回结果
            result = self._format_summary_result(summary, intent)
            
            return result
            
        elif action == "get_recent_summaries":
            # 返回错误信息，因为数据库功能已被删除
            raise ValueError("已不支持get_recent_summaries操作，请使用API参数传递历史数据")
            
        else:
            raise ValueError(f"不支持的操作: {action}")
    
    def _format_summary_result(self, summary: PartialSummary, intent: Dict[str, Any]) -> Dict[str, Any]:
        """根据intent字段格式化总结结果"""
        result = {
            "summary": {
                "session_id": summary.session_id,
                "timestamp": summary.timestamp.isoformat(),
                "markdown_content": summary.markdown_content,
                "word_count": summary.word_count,
                "course_tags": summary.course_tags
            }
        }
        
        # 添加元数据
        if intent.get("include_metadata", False):
            result["metadata"] = {
                "service_version": self.version,
                "generated_at": datetime.now().isoformat(),
                "model_used": self.model_name,
                "content_length": len(summary.markdown_content),
                "tag_count": len(summary.course_tags)
            }
        
        # 添加统计信息
        if intent.get("include_statistics", False):
            result["statistics"] = {
                "markdown_sections": len([line for line in summary.markdown_content.split('\n') if line.startswith('#')]),
                "key_concepts_count": summary.markdown_content.count('🔑'),
                "important_points_count": summary.markdown_content.count('📚'),
                "reminders_count": summary.markdown_content.count('💡')
            }
        
        return result
    
    def _format_summaries_list(self, summaries: List[Dict[str, Any]], intent: Dict[str, Any]) -> Dict[str, Any]:
        """格式化总结列表"""
        result = {
            "summaries": summaries,
            "total_count": len(summaries)
        }
        
        if intent.get("include_statistics", False):
            total_words = sum(s.get("word_count", 0) for s in summaries)
            all_tags = []
            for s in summaries:
                if s.get("course_tags"):
                    all_tags.extend(s["course_tags"])
            
            result["statistics"] = {
                "total_word_count": total_words,
                "unique_tags": list(set(all_tags)),
                "average_word_count": total_words / len(summaries) if summaries else 0,
                "date_range": {
                    "earliest": min(s["timestamp"] for s in summaries) if summaries else None,
                    "latest": max(s["timestamp"] for s in summaries) if summaries else None
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
    
    def generate_summary(self, 
                        course_profile: Dict[str, Any], 
                        transcript_text: str, 
                        session_id: str = None) -> PartialSummary:
        """
        生成阶段性总结
        
        Args:
            course_profile: 课程画像字典（来自MaterialSvc）
            transcript_text: 转录文本
            session_id: 会话ID，如果为None则自动生成
            
        Returns:
            PartialSummary: 生成的总结对象
        """
        if not transcript_text or len(transcript_text.strip()) < 50:
            raise ValueError("转录文本过短，无法生成有意义的总结")
        
        if session_id is None:
            session_id = f"session_{int(time.time())}"
        
        # 构建提示词
        system_prompt = self._build_system_prompt(course_profile)
        user_prompt = f"请为以下课堂转录内容生成阶段性总结：\n\n{transcript_text}"
        
        # 调用GPT
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            summary_content = response.choices[0].message.content.strip()
            
            # 提取标签
            course_tags = self._extract_tags(summary_content, course_profile)
            
            # 统计字数
            word_count = self._count_words(summary_content)
            
            return PartialSummary(
                session_id=session_id,
                timestamp=datetime.now(),
                markdown_content=summary_content,
                course_tags=course_tags,
                word_count=word_count
            )
            
        except Exception as e:
            raise Exception(f"GPT总结生成失败: {str(e)}")
    
    def _build_system_prompt(self, course_profile: Dict[str, Any]) -> str:
        """构建系统提示词"""
        keywords_str = ', '.join(course_profile.get('keywords', [])[:15])
        objectives_str = '; '.join(course_profile.get('learning_objectives', []))
        
        return f"""你是专业的课堂内容总结助手。请根据课堂转录文本生成简洁的阶段性总结。

课程信息：
- 标题：{course_profile.get('main_title', '')}
- 副标题：{course_profile.get('subtitle', '')}
- 核心关键词：{keywords_str}
- 学习目标：{objectives_str}

要求：
1. 严格使用Markdown格式
2. 总字数不超过300字
3. 结构：
   - ## 📚 本段要点 (3-4个要点)
   - ## 🔑 关键概念 (3-5个术语及说明)
   - ## 💡 重要提醒 (如有注意事项)

4. 在末尾添加标签：`标签：#概念1 #概念2 #概念3`
5. 只总结转录中实际提到的内容，不要添加额外信息"""
    
    def _extract_tags(self, summary_content: str, course_profile: Dict[str, Any]) -> List[str]:
        """提取课程标签"""
        tags = []
        
        # 从总结中提取标签
        lines = summary_content.split('\n')
        for line in lines:
            if '标签：' in line or '标签:' in line:
                hashtag_pattern = r'#(\w+)'
                found_tags = re.findall(hashtag_pattern, line)
                tags.extend(found_tags)
                break
        
        # 如果没找到标签，从课程关键词中选取
        if not tags:
            keywords = course_profile.get('keywords', [])
            tags = keywords[:5]
        
        return list(set(tags))[:10]  # 去重，最多10个
    
    def _count_words(self, text: str) -> int:
        """统计字数（中英文混合）"""
        # 移除Markdown标记
        text = re.sub(r'[#*`\-\[\]()]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        # 统计中文字符和英文单词
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        
        return chinese_chars + english_words


def main():
    """主函数示例 - 演示标准化API请求体和回复体"""
    try:
        # 初始化服务
        partial_summ_svc = PartialSummSvc()
        
        # 模拟课程画像数据
        sample_course_profile = {
            "main_title": "Introduction to Computer Graphics",
            "subtitle": "Module 1. Lecture 2",
            "keywords": ["coordinate systems", "Cartesian", "polar", "vectors", "matrices"],
            "learning_objectives": ["Understand coordinate systems", "Learn transformations"]
        }
        
        # 模拟转录文本
        sample_transcript = """
        Today we're going to talk about coordinate systems in computer graphics. 
        The most fundamental coordinate system we use is the Cartesian coordinate system, 
        developed by René Descartes. In this system, we use x and y coordinates to represent 
        points in 2D space. For 3D graphics, we add a z-axis. The conversion between different 
        coordinate systems, such as from polar to Cartesian coordinates, uses the formulas 
        x = r cos(α) and y = r sin(α). This is essential for computer graphics because 
        we need to transform objects from one coordinate system to another for rendering.
        """
        
        # 测试请求1：生成阶段性总结
        request_data_1 = {
            "version": "1.0.0",
            "request_id": str(uuid.uuid4()),
            "source": {
                "timestamp": datetime.now().isoformat(),
                "page": "/class/123/summary",
                "app": {"name": "classguru-web", "version": "1.4.2"},
                "locale": "zh-CN",
                "timezone": "Asia/Shanghai"
            },
            "intent": {
                "action": "generate_summary",
                "course_profile": sample_course_profile,
                "transcript_text": sample_transcript,
                "session_id": "demo_session"
            },
            "expect": {
                "include_metadata": True,
                "include_statistics": True
            }
        }
        
        print("=== 请求体1 (生成阶段性总结) ===")
        print(json.dumps(request_data_1, indent=2, ensure_ascii=False))
        
        response_1 = partial_summ_svc.handle_request(request_data_1)
        
        print("\n=== 回复体1 ===")
        print(json.dumps(response_1, indent=2, ensure_ascii=False))
        
        print("\n📋 API使用方法：")
        print("1. 设置环境变量：$env:OPENAI_API_KEY='your_api_key'")
        print("2. 创建服务实例：partial_summ_svc = PartialSummSvc()")
        print("3. 发送API请求：response = partial_summ_svc.handle_request(request_data)")
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")


def demo_api_usage():
    """API使用示例"""
    request_example = {
        "version": "1.0.0",
        "request_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
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
            "include_metadata": True,
            "include_statistics": True
        }
    }
    
    print("=== API请求示例模板 ===")
    print(json.dumps(request_example, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
