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
class FinalReport:
    """课后总结报告数据结构"""
    report_id: str
    session_id: str
    generated_at: datetime
    markdown_content: str
    word_count: int
    section_count: int
    source_summary: Dict[str, Any]  # 源数据摘要

class FinalReportSvc:
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
        
        if action == "generate_final_report":
            # 生成课后总结报告
            transcript_text = intent.get("transcript_text")
            summaries_markdown = intent.get("summaries_markdown")
            user_dialog_text = intent.get("user_dialog_text")
            course_profile_json = intent.get("course_profile_json")
            session_id = intent.get("session_id")
            
            # 验证必需参数
            if not transcript_text:
                raise ValueError("generate_final_report操作需要transcript_text参数")
            if not summaries_markdown:
                raise ValueError("generate_final_report操作需要summaries_markdown参数")
            if not course_profile_json:
                raise ValueError("generate_final_report操作需要course_profile_json参数")
            
            # 生成报告
            final_report = self._generate_report_internal(
                transcript_text=transcript_text,
                summaries_markdown=summaries_markdown,
                user_dialog_text=user_dialog_text or "",
                course_profile_json=course_profile_json,
                session_id=session_id
            )
            
            # 根据intent字段格式化返回结果
            result = self._format_report_result(final_report, intent)
            
            return result
            
        else:
            raise ValueError(f"不支持的操作: {action}")
    
    def _generate_report_internal(self, 
                                 transcript_text: str, 
                                 summaries_markdown: str, 
                                 user_dialog_text: str, 
                                 course_profile_json: str,
                                 session_id: str = None) -> FinalReport:
        """内部报告生成方法"""
        if session_id is None:
            session_id = f"report_{int(datetime.now().timestamp())}"
        
        # 解析 CourseProfile JSON
        try:
            course_profile = json.loads(course_profile_json)
        except json.JSONDecodeError:
            raise ValueError("Invalid CourseProfile JSON format.")
        
        # 生成报告内容
        markdown_content = self._generate_report_content(
            transcript_text, summaries_markdown, user_dialog_text, course_profile
        )
        
        # 计算统计信息
        word_count = self._count_words(markdown_content)
        section_count = self._count_sections(markdown_content)
        
        # 构建源数据摘要
        source_summary = {
            "transcript_length": len(transcript_text),
            "summaries_length": len(summaries_markdown),
            "dialog_length": len(user_dialog_text),
            "course_title": course_profile.get("main_title", "Unknown"),
            "keywords_count": len(course_profile.get("keywords", [])),
            "objectives_count": len(course_profile.get("learning_objectives", []))
        }
        
        return FinalReport(
            report_id=str(uuid.uuid4()),
            session_id=session_id,
            generated_at=datetime.now(),
            markdown_content=markdown_content,
            word_count=word_count,
            section_count=section_count,
            source_summary=source_summary
        )
    
    def _format_report_result(self, final_report: FinalReport, intent: Dict[str, Any]) -> Dict[str, Any]:
        """根据intent字段格式化报告结果"""
        result = {
            "final_report": {
                "report_id": final_report.report_id,
                "session_id": final_report.session_id,
                "generated_at": final_report.generated_at.isoformat(),
                "markdown_content": final_report.markdown_content,
                "word_count": final_report.word_count,
                "section_count": final_report.section_count
            }
        }
        
        # 添加元数据
        if intent.get("include_metadata", False):
            result["metadata"] = {
                "service_version": self.version,
                "model_used": "gpt-4o-mini",
                "generation_timestamp": datetime.now().isoformat(),
                "content_length": len(final_report.markdown_content),
                "processing_summary": "Three-tier structured final report generated"
            }
        
        # 添加源数据摘要
        if intent.get("include_source_summary", False):
            result["source_summary"] = final_report.source_summary
        
        # 添加统计信息
        if intent.get("include_statistics", False):
            result["statistics"] = {
                "content_breakdown": {
                    "level_1_items": final_report.markdown_content.count("## "),
                    "level_2_items": final_report.markdown_content.count("### "),
                    "level_3_items": final_report.markdown_content.count("#### ")
                },
                "formatting_elements": {
                    "bold_items": final_report.markdown_content.count("**") // 2,
                    "bullet_points": final_report.markdown_content.count("- "),
                    "numbered_lists": len([line for line in final_report.markdown_content.split('\n') if line.strip().startswith(tuple('123456789'))])
                }
            }
        
        return result
    
    def _count_words(self, text: str) -> int:
        """统计字数（中英文混合）"""
        import re
        # 移除Markdown标记
        text = re.sub(r'[#*`\-\[\]()]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        # 统计中文字符和英文单词
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        
        return chinese_chars + english_words
    
    def _count_sections(self, text: str) -> int:
        """统计章节数量"""
        lines = text.split('\n')
        sections = [line for line in lines if line.strip().startswith('#')]
        return len(sections)
    
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
    
    def _generate_report_content(self, transcript_text: str, summaries_markdown: str, 
                               user_dialog_text: str, course_profile: Dict[str, Any]) -> str:
        """
        生成三层次的课后总结报告。

        :param transcript_text: 全部转录文本 (str)
        :param summaries_markdown: 所有阶段性总结 (Markdown str)
        :param user_dialog_text: 用户与课堂对话记录 (str)
        :param course_profile: CourseProfile 字典
        :return: Markdown 格式的总结报告 (str)
        """
        # 构建提示词
        prompt = f"""
        你是一个教育总结专家。请基于以下输入生成一个三层次的课后总结报告。报告必须严格分层，结构清晰，便于二次学习。使用学习友好的Markdown模板，包括标题、粗体强调和有序列表。

        输入数据：
        - 课程转录文本：{transcript_text}
        - 阶段性总结：{summaries_markdown}
        - 用户对话记录：{user_dialog_text}
        - 课程画像（CourseProfile）：{json.dumps(course_profile, ensure_ascii=False)}

        输出格式（Markdown）：
        # 课后总结报告
        ## 1. 关键知识点
        - 知识点1
        - 知识点2
        - ...

        ## 2. 每个知识点的细节
        ### 知识点1
        - 细节1
        - 细节2
        - ...

        ### 知识点2
        - 细节1
        - 细节2
        - ...

        ## 3. 对细节的扩展说明/解释
        ### 知识点1 - 细节1
        - 扩展解释1
        - 扩展解释2
        - ...

        ### 知识点1 - 细节2
        - 扩展解释1
        - ...

        （以此类推，确保每个知识点的每个细节都有扩展）

        要点：
        - 提取并整合所有输入中的核心内容。
        - 关键知识点应覆盖课程主要主题（如从CourseProfile的outline和keywords中提取）。
        - 细节应基于转录、总结和对话，提供具体描述。
        - 扩展说明应包括解释、示例、相关公式（如从formulas_symbols中）和实际应用。
        - 保持客观、准确，确保报告全面但简洁。
        - 使用粗体突出关键术语。
        """

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant specialized in educational summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=4096
        )

        report_markdown = response.choices[0].message.content.strip()
        return report_markdown

def main():
    """主函数示例 - 演示标准化API请求体和回复体"""
    try:
        # 初始化服务
        svc = FinalReportSvc()
        
        # 模拟输入数据
        sample_transcript_text = """
        Welcome to the lecture on Introduction to Computer Graphics. Today we discuss coordinate systems and basic math.
        We start with Cartesian coordinates, where points are (x, y). Then polar coordinates: x = r cos(theta), y = r sin(theta).
        We also cover vectors and matrices. The Pythagorean theorem states that c² = a² + b² for right triangles.
        Coordinate transformations are essential in computer graphics for rendering objects in different coordinate systems.
        We discussed the importance of understanding mathematical foundations before diving into complex graphics algorithms.
        """

        sample_summaries_markdown = """
        ## 阶段总结1
        ### 📚 本段要点
        - 介绍了计算机图形学的基础概念
        - 讲解了笛卡尔坐标系的基本定义
        - 强调了数学基础的重要性
        
        ### 🔑 关键概念
        - **笛卡尔坐标系**: 使用(x, y)表示平面上的点
        - **坐标系转换**: 在不同坐标系之间转换点的位置
        
        标签：#坐标系 #笛卡尔 #数学基础

        ## 阶段总结2
        ### 📚 本段要点
        - 详细讨论了极坐标系的概念
        - 提供了极坐标到笛卡尔坐标的转换公式
        - 介绍了向量和矩阵的基本概念
        
        ### 🔑 关键概念
        - **极坐标**: 使用(r, θ)表示点的位置
        - **转换公式**: x = r cos(θ), y = r sin(θ)
        - **向量**: 有大小和方向的量
        
        标签：#极坐标 #向量 #矩阵
        """

        sample_user_dialog_text = """
        用户: 什么是勾股定理？
        AI助手: 勾股定理是一个基本的几何定理，表示在直角三角形中，斜边的平方等于两直角边平方的和，即 c² = a² + b²。

        用户: 如何从极坐标转换为笛卡尔坐标？
        AI助手: 极坐标到笛卡尔坐标的转换公式是：x = r cos(α)，y = r sin(α)，其中r是极径，α是极角。

        用户: 向量的点积是什么？
        AI助手: 向量的点积是两个向量的数量积，公式为 a·b = |a| |b| cos(θ)，其中θ是两向量间的夹角。
        """

        sample_course_profile_json = '''
        {
          "main_title": "Introduction to Computer Graphics and Foundation Mathematics",
          "subtitle": "Module 1. Lecture 2",
          "introduction": "This course introduces the fundamental concepts of computer graphics and the mathematical foundations necessary for understanding and creating digital images.",
          "keywords": [
            "geometry",
            "coordinates",
            "mathematical functions",
            "Cartesian coordinates",
            "polar coordinates",
            "vectors",
            "matrices",
            "trigonometry",
            "Pythagorean theorem",
            "computer graphics"
          ],
          "outline": [
            "Coordinate systems",
            "Analytic functions",
            "Pythagorean theorem",
            "Trigonometry",
            "Matrices",
            "Vectors",
            "Mathematical functions"
          ],
          "formulas_symbols": [
            {
              "symbol": "c² = a² + b²",
              "description": "Pythagorean theorem"
            },
            {
              "symbol": "x = r cos(α)",
              "description": "Conversion from polar to Cartesian coordinates"
            },
            {
              "symbol": "y = r sin(α)",
              "description": "Conversion from polar to Cartesian coordinates"
            },
            {
              "symbol": "a·b = |a| |b| cos(θ)",
              "description": "Dot product of vectors a and b"
            }
          ],
          "learning_objectives": [
            "Understand the definition of geometry with a computer using digital representation.",
            "Develop skills in creating images using raw mathematics.",
            "Learn to break down complicated problems into basic elements."
          ]
        }
        '''
        
        # 测试请求：生成课后总结报告
        request_data = {
            "version": "1.0.0",
            "request_id": str(uuid.uuid4()),
            "source": {
                "timestamp": datetime.now().isoformat(),
                "page": "/class/123/final_report",
                "app": {"name": "classguru-web", "version": "1.4.2"},
                "locale": "zh-CN",
                "timezone": "Asia/Shanghai"
            },
            "intent": {
                "action": "generate_final_report",
                "transcript_text": sample_transcript_text,
                "summaries_markdown": sample_summaries_markdown,
                "user_dialog_text": sample_user_dialog_text,
                "course_profile_json": sample_course_profile_json,
                "session_id": "final_report_demo_session",
                "include_metadata": True,
                "include_source_summary": True,
                "include_statistics": True
            },
            "expect": None
        }
        
        print("=== 请求体 (生成课后总结报告) ===")
        print(json.dumps(request_data, indent=2, ensure_ascii=False))
        
        response = svc.handle_request(request_data)
        
        print("\n=== 回复体 ===")
        print(json.dumps(response, indent=2, ensure_ascii=False))
        
        print("\n📋 API使用方法：")
        print("1. 设置环境变量：$env:OPENAI_API_KEY='your_api_key'")
        print("2. 创建服务实例：svc = FinalReportSvc()")
        print("3. 准备请求数据（包含transcript_text、summaries_markdown、user_dialog_text、course_profile_json）")
        print("4. 发送API请求：response = svc.handle_request(request_data)")
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")


if __name__ == "__main__":
    main()