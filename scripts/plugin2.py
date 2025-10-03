"""
实时转录服务（STT Service）
功能：处理课堂实时语音流，实现实时转录和可选翻译
"""

import asyncio
import json
import logging
import time
import base64
import struct
import uuid
import os
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict
from enum import Enum
import threading
from queue import Queue, Empty
from datetime import datetime
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
import openai
from collections import deque


# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TranscriptionState(Enum):
    """转录状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class AudioConfig:
    """音频配置参数"""
    sample_rate: int = 16000          # 采样率 16kHz
    channels: int = 1                 # 单声道
    encoding: str = "opus"            # Opus 压缩
    bitrate: int = 32000             # 自适应码率起始值
    frame_duration: int = 20          # 帧长度 (ms)
    buffer_size: int = 1024          # 缓冲区大小


@dataclass
class TranscriptionResult:
    """转录结果数据结构"""
    timestamp: float
    text: str
    confidence: float
    is_final: bool
    language: str = "en"
    translated_text: Optional[str] = None


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
class ConnectionStats:
    """连接统计信息"""
    bytes_received: int = 0
    frames_processed: int = 0
    reconnect_count: int = 0
    avg_latency: float = 0.0
    jitter_buffer_size: int = 0


class JitterBuffer:
    """抖动缓冲区，处理网络不稳定"""
    
    def __init__(self, max_size: int = 10):
        self.buffer = deque(maxlen=max_size)
        self.sequence_number = 0
        self.expected_seq = 0
        
    def add_frame(self, audio_data: bytes, seq_num: int) -> Optional[bytes]:
        """
        添加音频帧到缓冲区
        
        Args:
            audio_data: 音频数据
            seq_num: 序列号
            
        Returns:
            可以播放的音频帧，如果缓冲区未满则返回None
        """
        self.buffer.append((seq_num, audio_data))
        
        # 按序列号排序
        self.buffer = deque(sorted(self.buffer, key=lambda x: x[0]))
        
        # 如果有连续的帧可以输出
        if self.buffer and self.buffer[0][0] == self.expected_seq:
            seq, data = self.buffer.popleft()
            self.expected_seq += 1
            return data
            
        return None
    
    def get_buffer_size(self) -> int:
        """获取缓冲区大小"""
        return len(self.buffer)


@dataclass
class UserSession:
    """用户会话数据结构"""
    session_id: str
    connection_id: str
    websocket: Any
    jitter_buffer: JitterBuffer
    audio_queue: Queue
    language: str = "en"
    translate_to: Optional[str] = None
    display_subtitles: bool = False
    enable_translation: bool = False
    created_at: datetime = None
    stats: ConnectionStats = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.stats is None:
            self.stats = ConnectionStats()


class ConnectionManager:
    """管理多个WebSocket连接和会话"""
    
    def __init__(self, max_connections: int = 50):
        self.max_connections = max_connections
        self.active_sessions: Dict[str, UserSession] = {}  # session_id -> UserSession
        self.connection_to_session: Dict[str, str] = {}    # connection_id -> session_id
        self.websocket_to_connection: Dict[Any, str] = {}  # websocket -> connection_id
        
    def create_session(self, websocket, session_id: str = None, connection_id: str = None) -> UserSession:
        """创建新会话"""
        if len(self.active_sessions) >= self.max_connections:
            raise Exception(f"超过最大连接数限制: {self.max_connections}")
        
        if session_id is None:
            session_id = f"session_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        if connection_id is None:
            connection_id = str(uuid.uuid4())
        
        # 检查会话是否已存在
        if session_id in self.active_sessions:
            raise Exception(f"会话ID已存在: {session_id}")
        
        # 创建会话
        session = UserSession(
            session_id=session_id,
            connection_id=connection_id,
            websocket=websocket,
            jitter_buffer=JitterBuffer(),
            audio_queue=Queue(maxsize=1000)
        )
        
        # 注册映射关系
        self.active_sessions[session_id] = session
        self.connection_to_session[connection_id] = session_id
        self.websocket_to_connection[websocket] = connection_id
        
        logger.info(f"会话创建成功: {session_id}, 连接ID: {connection_id}, 当前活跃会话数: {len(self.active_sessions)}")
        return session
    
    def get_session_by_websocket(self, websocket) -> Optional[UserSession]:
        """通过WebSocket获取会话"""
        connection_id = self.websocket_to_connection.get(websocket)
        if connection_id:
            session_id = self.connection_to_session.get(connection_id)
            if session_id:
                return self.active_sessions.get(session_id)
        return None
    
    def get_session_by_id(self, session_id: str) -> Optional[UserSession]:
        """通过会话ID获取会话"""
        return self.active_sessions.get(session_id)
    
    def remove_session(self, websocket) -> bool:
        """移除会话"""
        connection_id = self.websocket_to_connection.get(websocket)
        if not connection_id:
            return False
        
        session_id = self.connection_to_session.get(connection_id)
        if not session_id:
            return False
        
        # 清理所有映射关系
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        if connection_id in self.connection_to_session:
            del self.connection_to_session[connection_id]
        if websocket in self.websocket_to_connection:
            del self.websocket_to_connection[websocket]
        
        logger.info(f"会话移除成功: {session_id}, 连接ID: {connection_id}, 当前活跃会话数: {len(self.active_sessions)}")
        return True
    
    def get_active_session_count(self) -> int:
        """获取活跃会话数"""
        return len(self.active_sessions)
    
    def get_all_sessions(self) -> List[UserSession]:
        """获取所有活跃会话"""
        return list(self.active_sessions.values())





class STTService:
    """实时转录服务"""
    
    def __init__(self, openai_api_key: Optional[str] = None, max_connections: int = 50):
        """
        初始化STT服务
        
        Args:
            openai_api_key: OpenAI API密钥，如果为None则从环境变量获取
            max_connections: 最大并发连接数
        """
        # 获取API密钥
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
        
        # 版本管理
        self.version = "1.0.0"
        
        # 连接管理
        self.connection_manager = ConnectionManager(max_connections=max_connections)
        
        # 服务状态
        self.state = TranscriptionState.STOPPED
        self.audio_config = AudioConfig()
        
        # WebSocket服务器
        self.ws_server = None
        
        # 回调函数
        self.transcription_callbacks: List[Callable] = []
        self.error_callbacks: List[Callable] = []
        self.state_change_callbacks: List[Callable] = []
        
        # 后台任务
        self.audio_processor_tasks: Dict[str, asyncio.Task] = {}  # session_id -> task
        self.transcription_tasks: Dict[str, asyncio.Task] = {}    # session_id -> task
    
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
        
        if action == "start_transcription":
            # 启动转录服务
            config = intent.get("config", {})
            self._apply_config(config)
            
            # 返回服务状态和配置信息
            result = {
                "service_status": self.state.value,
                "audio_config": asdict(self.audio_config),
                "websocket_url": f"ws://localhost:{config.get('port', 8765)}",
                "translation_enabled": self.enable_translation,
                "target_language": self.translation_target_lang
            }
            
            return result
            
        elif action == "get_status":
            # 获取服务状态
            result = {
                "service_status": self.state.value,
                "stats": asdict(self.stats),
                "translation_enabled": self.enable_translation,
                "subtitle_display": self.display_subtitles
            }
            
            return result
            
        elif action == "transcribe_audio":
            # 直接转录音频数据
            audio_data = intent.get("audio_data")
            language = intent.get("language", "en")
            
            if not audio_data:
                raise ValueError("transcribe_audio操作需要audio_data参数")
            
            # 解码base64音频数据
            try:
                audio_bytes = base64.b64decode(audio_data)
            except Exception:
                raise ValueError("audio_data必须是有效的base64编码")
            
            # 同步转录（简化版）
            transcription_result = self._transcribe_audio_sync(audio_bytes, language)
            
            # 根据intent字段格式化返回结果
            result = self._format_transcription_result(transcription_result, intent)
            
            return result
            
        else:
            raise ValueError(f"不支持的操作: {action}")
    
    def _format_transcription_result(self, transcription_result: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        """根据intent字段格式化转录结果"""
        result = {
            "timestamp": transcription_result["timestamp"],
            "subtitle": {
                "original": transcription_result.get("original_text"),
                "translated": transcription_result.get("translated_text")
            },
            "language": transcription_result["language"],
            "confidence": transcription_result["confidence"]
        }
        
        # 添加额外的元数据
        if intent.get("include_metadata", False):
            result["metadata"] = {
                "service_version": self.version,
                "processed_at": datetime.now().isoformat(),
                "audio_duration": transcription_result.get("duration", 0.0),
                "translation_enabled": self.enable_translation,
                "target_language": self.translation_target_lang if self.enable_translation else None
            }
        
        # 添加技术细节
        if intent.get("include_technical_details", False):
            result["technical_details"] = {
                "audio_config": asdict(self.audio_config),
                "model_used": "whisper-1",
                "processing_time": transcription_result.get("processing_time", 0.0)
            }
        
        return result
    
    def _apply_config(self, config: Dict[str, Any]) -> None:
        """应用配置参数"""
        # 更新音频配置
        if "audio_config" in config:
            audio_config = config["audio_config"]
            for key, value in audio_config.items():
                if hasattr(self.audio_config, key):
                    setattr(self.audio_config, key, value)
        
        # 更新翻译配置
        if "enable_translation" in config:
            self.enable_translation = config["enable_translation"]
        
        if "target_language" in config:
            self.translation_target_lang = config["target_language"]
        
        # 更新字幕显示
        if "display_subtitles" in config:
            self.display_subtitles = config["display_subtitles"]
    
    def _transcribe_audio_sync(self, audio_data: bytes, language: str = "en") -> Dict[str, Any]:
        """同步转录音频数据"""
        start_time = time.time()
        
        try:
            import tempfile
            
            # 创建临时音频文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                wav_header = self._create_wav_header(
                    len(audio_data),
                    self.audio_config.channels,
                    self.audio_config.sample_rate,
                    16
                )
                temp_file.write(wav_header)
                temp_file.write(audio_data)
                temp_file.flush()
                
                # 调用OpenAI转录API（支持直接翻译）
                with open(temp_file.name, 'rb') as audio_file:
                    # 根据是否需要翻译选择不同的API调用方式
                    if self.enable_translation and language != self.translation_target_lang:
                        # 使用翻译功能 - 返回翻译后的文本
                        response = self.client.audio.translations.create(
                            model="whisper-1",
                            file=audio_file,
                            response_format="verbose_json"
                        )
                        # 同时获取原文（需要额外调用）
                        audio_file.seek(0)
                        original_response = self.client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language=language,
                            response_format="verbose_json"
                        )
                        
                        original_text = original_response.text
                        translated_text = response.text
                        confidence = max(getattr(response, 'confidence', 0.9), 
                                       getattr(original_response, 'confidence', 0.9))
                        duration = max(getattr(response, 'duration', 0.0),
                                     getattr(original_response, 'duration', 0.0))
                    else:
                        # 仅转录
                        response = self.client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language=language,
                            response_format="verbose_json"
                        )
                        original_text = response.text
                        translated_text = None
                        confidence = getattr(response, 'confidence', 0.9)
                        duration = getattr(response, 'duration', 0.0)
                
                # 清理临时文件
                os.unlink(temp_file.name)
                
                processing_time = time.time() - start_time
                
                # 构建结果
                result = {
                    "timestamp": time.time(),
                    "original_text": original_text,
                    "translated_text": translated_text,
                    "language": language,
                    "confidence": confidence,
                    "duration": duration,
                    "processing_time": processing_time
                }
                
                return result
                
        except Exception as e:
            raise Exception(f"音频转录失败: {str(e)}")
    
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
    
    def add_transcription_callback(self, callback: Callable[[TranscriptionResult], None]) -> None:
        """添加转录结果回调函数"""
        self.transcription_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable[[str], None]) -> None:
        """添加错误回调函数"""
        self.error_callbacks.append(callback)
    
    def add_state_change_callback(self, callback: Callable[[TranscriptionState], None]) -> None:
        """添加状态变化回调函数"""
        self.state_change_callbacks.append(callback)
    
    def _change_state(self, new_state: TranscriptionState) -> None:
        """改变服务状态并触发回调"""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            logger.info(f"状态变化: {old_state.value} -> {new_state.value}")
            
            for callback in self.state_change_callbacks:
                try:
                    callback(new_state)
                except Exception as e:
                    logger.error(f"状态回调错误: {e}")
    
    def _trigger_error(self, error_message: str) -> None:
        """触发错误回调"""
        logger.error(error_message)
        for callback in self.error_callbacks:
            try:
                callback(error_message)
            except Exception as e:
                logger.error(f"错误回调失败: {e}")
    
    def _trigger_transcription(self, result: TranscriptionResult) -> None:
        """触发转录结果回调"""
        if self.display_subtitles:  # 只有当字幕显示开启时才触发回调
            for callback in self.transcription_callbacks:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"转录回调错误: {e}")
    
    async def start_websocket_server(self, host: str = "localhost", port: int = 8765) -> None:
        """
        启动WebSocket服务器接收音频流
        
        Args:
            host: 服务器主机地址
            port: 服务器端口
        """
        try:
            self._change_state(TranscriptionState.STARTING)
            
            async def handle_client(websocket, path):
                """处理客户端连接（支持多连接）"""
                session = None
                logger.info(f"客户端尝试连接: {websocket.remote_address}")
                
                try:
                    # 等待客户端发送初始化消息
                    init_message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    init_data = json.loads(init_message)
                    
                    # 验证初始化消息
                    if init_data.get("type") != "init":
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": "首条消息必须是初始化消息"
                        }))
                        return
                    
                    # 创建会话
                    session_id = init_data.get("session_id")
                    session = self.connection_manager.create_session(websocket, session_id)
                    
                    # 应用会话配置
                    session.language = init_data.get("language", "en")
                    session.translate_to = init_data.get("translate_to")
                    session.enable_translation = bool(session.translate_to)
                    session.display_subtitles = init_data.get("display_subtitles", True)
                    
                    # 发送初始化确认
                    await websocket.send(json.dumps({
                        "type": "init_response",
                        "session_id": session.session_id,
                        "connection_id": session.connection_id,
                        "status": "connected",
                        "server_version": self.version
                    }))
                    
                    self._change_state(TranscriptionState.RUNNING)
                    
                    # 启动会话专用的处理任务
                    audio_task = asyncio.create_task(self._process_session_audio(session))
                    transcription_task = asyncio.create_task(self._session_transcription_worker(session))
                    
                    self.audio_processor_tasks[session.session_id] = audio_task
                    self.transcription_tasks[session.session_id] = transcription_task
                    
                    # 处理音频流
                    await self._handle_session_audio_stream(session)
                    
                except asyncio.TimeoutError:
                    logger.warning("客户端初始化超时")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "初始化超时，请在30秒内发送init消息"
                    }))
                except ConnectionClosed:
                    logger.info(f"客户端连接关闭: {session.session_id if session else 'unknown'}")
                except Exception as e:
                    logger.error(f"处理客户端错误: {e}")
                    if session:
                        await self._send_session_error(session, f"客户端处理错误: {e}")
                finally:
                    # 清理会话资源
                    if session:
                        await self._cleanup_session(session)
            
            # 启动WebSocket服务器
            self.ws_server = await websockets.serve(handle_client, host, port)
            logger.info(f"STT服务器启动于 ws://{host}:{port}，支持最多 {self.connection_manager.max_connections} 个并发连接")
            
        except Exception as e:
            self._change_state(TranscriptionState.ERROR)
            self._trigger_error(f"启动服务器失败: {e}")
            raise
    
    async def _handle_session_audio_stream(self, session) -> None:
        """处理单个会话的音频流数据"""
        sequence_number = 0
        
        async for message in session.websocket:
            try:
                if isinstance(message, str):
                    # 处理控制消息
                    await self._handle_session_control_message(session, json.loads(message))
                else:
                    # 处理音频数据
                    timestamp = time.time()
                    
                    # 更新会话统计信息
                    session.stats.bytes_received += len(message)
                    session.stats.frames_processed += 1
                    
                    # 添加到会话专用的抖动缓冲区
                    buffered_data = session.jitter_buffer.add_frame(message, sequence_number)
                    if buffered_data:
                        # 添加到会话专用的处理队列
                        if not session.audio_queue.full():
                            session.audio_queue.put((timestamp, buffered_data))
                        else:
                            logger.warning(f"会话 {session.session_id} 音频队列已满，丢弃帧")
                    
                    sequence_number += 1
                    
                    # 发送ACK确认
                    await session.websocket.send(json.dumps({
                        "type": "ack",
                        "session_id": session.session_id,
                        "sequence": sequence_number - 1,
                        "timestamp": timestamp
                    }))
                    
            except Exception as e:
                logger.error(f"会话 {session.session_id} 处理音频流错误: {e}")
                await self._send_session_error(session, f"会话音频流处理错误: {e}")
    
    async def _handle_session_control_message(self, session, message: Dict[str, Any]) -> None:
        """处理会话控制消息"""
        msg_type = message.get("type")
        
        if msg_type == "start_display":
            session.display_subtitles = True
            logger.info(f"会话 {session.session_id} 字幕显示已开启")
            await session.websocket.send(json.dumps({
                "type": "control_response",
                "session_id": session.session_id,
                "action": "start_display",
                "status": "success"
            }))
        elif msg_type == "stop_display":
            session.display_subtitles = False
            logger.info(f"会话 {session.session_id} 字幕显示已关闭")
            await session.websocket.send(json.dumps({
                "type": "control_response", 
                "session_id": session.session_id,
                "action": "stop_display",
                "status": "success"
            }))
        elif msg_type == "enable_translation":
            session.enable_translation = message.get("enabled", False)
            session.translate_to = message.get("target_lang", "zh")
            logger.info(f"会话 {session.session_id} 翻译功能: {'开启' if session.enable_translation else '关闭'}")
            await session.websocket.send(json.dumps({
                "type": "control_response",
                "session_id": session.session_id, 
                "action": "enable_translation",
                "status": "success",
                "translation_enabled": session.enable_translation
            }))
        elif msg_type == "ping":
            # 心跳检测
            await session.websocket.send(json.dumps({
                "type": "pong",
                "session_id": session.session_id,
                "timestamp": time.time()
            }))
    
    async def _send_session_error(self, session, error_message: str) -> None:
        """向特定会话发送错误消息"""
        try:
            await session.websocket.send(json.dumps({
                "type": "error",
                "session_id": session.session_id,
                "message": error_message,
                "timestamp": time.time()
            }))
        except Exception as e:
            logger.error(f"发送错误消息失败: {e}")
    
    async def _process_session_audio(self, session) -> None:
        """处理单个会话的音频队列"""
        audio_buffer = bytearray()
        
        while session.session_id in self.connection_manager.active_sessions:
            try:
                # 从会话队列获取音频数据
                try:
                    timestamp, audio_data = session.audio_queue.get(timeout=0.1)
                    
                    if audio_data:
                        audio_buffer.extend(audio_data)
                        
                        # 当缓冲区足够大时进行转录
                        if len(audio_buffer) >= 8192:  # 约0.5秒的音频
                            # 发送给转录处理
                            await self._transcribe_session_audio(session, bytes(audio_buffer))
                            audio_buffer.clear()
                            
                except:
                    # 队列为空，继续等待
                    pass
                
                await asyncio.sleep(0.01)  # 小延迟避免CPU占用过高
                
            except Exception as e:
                logger.error(f"会话 {session.session_id} 音频队列处理错误: {e}")
                await asyncio.sleep(0.1)
    
    async def _session_transcription_worker(self, session) -> None:
        """会话转录工作线程"""
        while session.session_id in self.connection_manager.active_sessions:
            try:
                # 更新会话统计信息
                session.stats.jitter_buffer_size = session.jitter_buffer.get_buffer_size()
                
                await asyncio.sleep(1.0)  # 每秒更新一次统计
                
            except Exception as e:
                logger.error(f"会话 {session.session_id} 转录工作线程错误: {e}")
                await asyncio.sleep(1.0)
    
    async def _transcribe_session_audio(self, session, audio_data: bytes) -> None:
        """
        使用OpenAI为特定会话进行音频转录
        """
        try:
            # 将音频数据转换为文件对象
            import tempfile
            
            # 创建临时音频文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                wav_header = self._create_wav_header(
                    len(audio_data),
                    self.audio_config.channels,
                    self.audio_config.sample_rate,
                    16  # 16位深度
                )
                temp_file.write(wav_header)
                temp_file.write(audio_data)
                temp_file.flush()
                
                # 调用OpenAI转录API
                with open(temp_file.name, 'rb') as audio_file:
                    if session.enable_translation and session.translate_to:
                        # 使用翻译API直接获取翻译结果
                        response = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.client.audio.translations.create(
                                model="whisper-1",
                                file=audio_file,
                                response_format="verbose_json"
                            )
                        )
                        translated_text = response.text
                        original_text = None
                    else:
                        # 仅转录
                        response = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.client.audio.transcriptions.create(
                                model="whisper-1",
                                file=audio_file,
                                language=session.language,
                                response_format="verbose_json"
                            )
                        )
                        original_text = response.text
                        translated_text = None
                
                # 处理转录结果
                if original_text or translated_text:
                    result = TranscriptionResult(
                        timestamp=time.time(),
                        text=original_text or translated_text,
                        confidence=getattr(response, 'confidence', 0.9),
                        is_final=True,
                        language=session.language if original_text else session.translate_to,
                        translated_text=translated_text if original_text else None
                    )
                    
                    # 发送转录结果到特定会话
                    if session.display_subtitles:
                        await session.websocket.send(json.dumps({
                            "type": "transcription",
                            "session_id": session.session_id,
                            "timestamp": result.timestamp,
                            "original_text": original_text,
                            "translated_text": translated_text,
                            "language": result.language,
                            "confidence": result.confidence
                        }))
                
                # 清理临时文件
                import os
                os.unlink(temp_file.name)
                
        except Exception as e:
            logger.error(f"会话 {session.session_id} 音频转录错误: {e}")
            await self._send_session_error(session, f"转录失败: {e}")
    
    async def _cleanup_session(self, session) -> None:
        """清理会话资源"""
        try:
            # 停止会话专用任务
            if session.session_id in self.audio_processor_tasks:
                task = self.audio_processor_tasks[session.session_id]
                if not task.done():
                    task.cancel()
                del self.audio_processor_tasks[session.session_id]
            
            if session.session_id in self.transcription_tasks:
                task = self.transcription_tasks[session.session_id]
                if not task.done():
                    task.cancel()
                del self.transcription_tasks[session.session_id]
            
            # 从连接管理器移除会话
            self.connection_manager.remove_session(session.websocket)
            
            logger.info(f"会话 {session.session_id} 资源清理完成")
            
        except Exception as e:
            logger.error(f"清理会话 {session.session_id} 资源时出错: {e}")
    
    async def _handle_audio_stream(self, websocket) -> None:
        """处理音频流数据"""
        sequence_number = 0
        
        async for message in websocket:
            try:
                if isinstance(message, str):
                    # 处理控制消息
                    await self._handle_control_message(json.loads(message))
                else:
                    # 处理音频数据
                    timestamp = time.time()
                    self.frame_timestamps.append(timestamp)
                    
                    # 更新统计信息
                    self.stats.bytes_received += len(message)
                    self.stats.frames_processed += 1
                    
                    # 添加到抖动缓冲区
                    buffered_data = self.jitter_buffer.add_frame(message, sequence_number)
                    if buffered_data:
                        # 添加到处理队列
                        if not self.audio_queue.full():
                            self.audio_queue.put((timestamp, buffered_data))
                        else:
                            logger.warning("音频队列已满，丢弃帧")
                    
                    sequence_number += 1
                    
                    # 发送ACK确认
                    await websocket.send(json.dumps({
                        "type": "ack",
                        "sequence": sequence_number - 1,
                        "timestamp": timestamp
                    }))
                    
            except Exception as e:
                logger.error(f"处理音频流错误: {e}")
                self._trigger_error(f"音频流处理错误: {e}")
    
    async def _handle_control_message(self, message: Dict[str, Any]) -> None:
        """处理控制消息"""
        msg_type = message.get("type")
        
        if msg_type == "start_display":
            self.display_subtitles = True
            logger.info("字幕显示已开启")
        elif msg_type == "stop_display":
            self.display_subtitles = False
            logger.info("字幕显示已关闭")
        elif msg_type == "enable_translation":
            self.enable_translation = message.get("enabled", False)
            self.translation_target_lang = message.get("target_lang", "zh")
            logger.info(f"翻译功能: {'开启' if self.enable_translation else '关闭'}")
        elif msg_type == "config":
            # 更新音频配置
            config = message.get("audio_config", {})
            for key, value in config.items():
                if hasattr(self.audio_config, key):
                    setattr(self.audio_config, key, value)
            logger.info(f"音频配置已更新: {config}")
    
    async def _process_audio_queue(self) -> None:
        """处理音频队列"""
        audio_buffer = bytearray()
        
        while self.state in [TranscriptionState.RUNNING, TranscriptionState.STARTING]:
            try:
                # 从队列获取音频数据
                timestamp, audio_data = await asyncio.get_event_loop().run_in_executor(
                    None, self._get_audio_from_queue
                )
                
                if audio_data:
                    audio_buffer.extend(audio_data)
                    
                    # 当缓冲区足够大时进行转录
                    if len(audio_buffer) >= 8192:  # 约0.5秒的音频
                        # 发送给转录处理
                        await self._queue_for_transcription(bytes(audio_buffer))
                        audio_buffer.clear()
                
                await asyncio.sleep(0.01)  # 小延迟避免CPU占用过高
                
            except Exception as e:
                logger.error(f"音频队列处理错误: {e}")
                await asyncio.sleep(0.1)
    
    def _get_audio_from_queue(self) -> tuple:
        """从音频队列获取数据（同步方法）"""
        try:
            return self.audio_queue.get(timeout=0.1)
        except Empty:
            return None, None
    
    async def _queue_for_transcription(self, audio_data: bytes) -> None:
        """将音频数据加入转录队列"""
        # 这里可以实现更复杂的队列管理
        # 简化实现：直接调用转录
        await self._transcribe_audio(audio_data)
    
    async def _transcription_worker(self) -> None:
        """转录工作线程"""
        while self.state in [TranscriptionState.RUNNING, TranscriptionState.STARTING]:
            try:
                # 更新统计信息
                if len(self.frame_timestamps) >= 2:
                    recent_timestamps = list(self.frame_timestamps)[-10:]
                    if len(recent_timestamps) > 1:
                        latencies = [recent_timestamps[i] - recent_timestamps[i-1] 
                                   for i in range(1, len(recent_timestamps))]
                        self.stats.avg_latency = sum(latencies) / len(latencies)
                
                self.stats.jitter_buffer_size = self.jitter_buffer.get_buffer_size()
                
                await asyncio.sleep(1.0)  # 每秒更新一次统计
                
            except Exception as e:
                logger.error(f"转录工作线程错误: {e}")
                await asyncio.sleep(1.0)
    
    async def _transcribe_audio(self, audio_data: bytes) -> None:
        """
        使用OpenAI进行音频转录
        
        Args:
            audio_data: 音频数据
        """
        try:
            # 将音频数据转换为文件对象
            import io
            import tempfile
            
            # 创建临时音频文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                wav_header = self._create_wav_header(
                    len(audio_data),
                    self.audio_config.channels,
                    self.audio_config.sample_rate,
                    16  # 16位深度
                )
                temp_file.write(wav_header)
                temp_file.write(audio_data)
                temp_file.flush()
                
                # 调用OpenAI转录API（支持直接翻译）
                with open(temp_file.name, 'rb') as audio_file:
                    if self.enable_translation:
                        # 使用翻译API直接获取翻译结果
                        response = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.client.audio.translations.create(
                                model="whisper-1",
                                file=audio_file,
                                response_format="verbose_json"
                            )
                        )
                        translated_text = response.text
                        original_text = None
                    else:
                        # 仅转录
                        response = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.client.audio.transcriptions.create(
                                model="whisper-1",
                                file=audio_file,
                                language="en",
                                response_format="verbose_json"
                            )
                        )
                        original_text = response.text
                        translated_text = None
                
                # 处理转录结果
                if original_text or translated_text:
                    result = TranscriptionResult(
                        timestamp=time.time(),
                        text=original_text or translated_text,
                        confidence=getattr(response, 'confidence', 0.9),
                        is_final=True,
                        language="en" if original_text else self.translation_target_lang,
                        translated_text=translated_text if original_text else None
                    )
                    
                    # 触发回调（传递完整的字幕信息）
                    self._trigger_transcription(result)
                
                # 清理临时文件
                import os
                os.unlink(temp_file.name)
                
        except Exception as e:
            logger.error(f"音频转录错误: {e}")
            self._trigger_error(f"转录失败: {e}")
    
    def _create_wav_header(self, data_size: int, channels: int, sample_rate: int, bits_per_sample: int) -> bytes:
        """创建WAV文件头"""
        byte_rate = sample_rate * channels * bits_per_sample // 8
        block_align = channels * bits_per_sample // 8
        
        header = struct.pack('<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + data_size,
            b'WAVE',
            b'fmt ',
            16,
            1,
            channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b'data',
            data_size
        )
        
        return header
    
    def start_subtitle_display(self) -> None:
        """开启字幕显示"""
        self.display_subtitles = True
        logger.info("字幕显示已开启")
    
    def stop_subtitle_display(self) -> None:
        """关闭字幕显示"""
        self.display_subtitles = False
        logger.info("字幕显示已关闭")
    
    def enable_translation_feature(self, target_lang: str = "zh") -> None:
        """启用翻译功能"""
        self.enable_translation = True
        self.translation_target_lang = target_lang
        logger.info(f"翻译功能已启用，目标语言: {target_lang}")
    
    def disable_translation_feature(self) -> None:
        """禁用翻译功能"""
        self.enable_translation = False
        logger.info("翻译功能已禁用")
    
    def get_stats(self) -> ConnectionStats:
        """获取连接统计信息"""
        return self.stats
    
    def get_state(self) -> TranscriptionState:
        """获取当前服务状态"""
        return self.state
    
    async def stop(self) -> None:
        """停止STT服务"""
        self._change_state(TranscriptionState.STOPPED)
        
        # 停止后台任务
        if self.audio_processor_task:
            self.audio_processor_task.cancel()
        if self.transcription_task:
            self.transcription_task.cancel()
        
        # 关闭WebSocket服务器
        if self.ws_server:
            self.ws_server.close()
            await self.ws_server.wait_closed()
        
        # 关闭WebSocket连接
        if self.websocket:
            await self.websocket.close()
        
        logger.info("STT服务已停止")


# 示例回调函数
def print_transcription(result: TranscriptionResult) -> None:
    """打印转录结果"""
    print(f"[{result.timestamp:.2f}] {result.text}")
    if result.translated_text:
        print(f"[翻译] {result.translated_text}")


def print_error(error: str) -> None:
    """打印错误信息"""
    print(f"错误: {error}")


def print_state_change(state: TranscriptionState) -> None:
    """打印状态变化"""
    print(f"状态: {state.value}")


async def main():
    """主函数示例"""
    try:
        # 创建STT服务
        stt_service = STTService()
        
        # 测试请求1：启动转录服务
        request_data_1 = {
            "version": "1.0.0",
            "request_id": str(uuid.uuid4()),
            "source": {
                "timestamp": datetime.now().isoformat(),
                "page": "/class/123/transcription",
                "app": {"name": "classguru-web", "version": "1.4.2"},
                "locale": "zh-CN",
                "timezone": "Asia/Shanghai"
            },
            "intent": {
                "action": "start_transcription",
                "config": {
                    "enable_translation": True,
                    "target_language": "zh",
                    "display_subtitles": True,
                    "audio_config": {
                        "sample_rate": 16000,
                        "channels": 1
                    }
                },
                "include_websocket_url": True,
                "include_config": True
            },
            "expect": None
        }
        
        print("=== 请求体1 (启动转录服务) ===")
        print(json.dumps(request_data_1, indent=2, ensure_ascii=False))
        
        response_1 = stt_service.handle_request(request_data_1)
        
        print("\n=== 回复体1 ===")
        print(json.dumps(response_1, indent=2, ensure_ascii=False))
        
        # 测试请求2：获取服务状态
        request_data_2 = {
            "version": "1.0.0",
            "request_id": str(uuid.uuid4()),
            "source": {
                "timestamp": datetime.now().isoformat(),
                "page": "/class/123/status",
                "app": {"name": "classguru-web", "version": "1.4.2"},
                "locale": "zh-CN",
                "timezone": "Asia/Shanghai"
            },
            "intent": {
                "action": "get_status",
                "include_stats": True
            },
            "expect": None
        }
        
        print("\n=== 请求体2 (获取状态) ===")
        print(json.dumps(request_data_2, indent=2, ensure_ascii=False))
        
        response_2 = stt_service.handle_request(request_data_2)
        
        print("\n=== 回复体2 ===")
        print(json.dumps(response_2, indent=2, ensure_ascii=False))
        
        # 测试请求3：音频转录（模拟）
        request_data_3 = {
            "version": "1.0.0",
            "request_id": str(uuid.uuid4()),
            "source": {
                "timestamp": datetime.now().isoformat(),
                "page": "/class/123/transcribe",
                "app": {"name": "classguru-web", "version": "1.4.2"},
                "locale": "zh-CN",
                "timezone": "Asia/Shanghai"
            },
            "intent": {
                "action": "transcribe_audio",
                "audio_data": "UklGRi4kAABXQVZFZm10IBAAAAABAAEAgD4AAIA+AAABACAAAP8=",  # 示例base64音频数据
                "language": "en",
                "include_metadata": True,
                "include_technical_details": True
            },
            "expect": None
        }
        
        print("\n=== 请求体3 (音频转录) ===")
        print(json.dumps(request_data_3, indent=2, ensure_ascii=False))
        
        # 注意：这个会失败因为音频数据是假的，但展示了请求格式
        try:
            response_3 = stt_service.handle_request(request_data_3)
            print("\n=== 回复体3 ===")
            print(json.dumps(response_3, indent=2, ensure_ascii=False))
        except Exception as e:
            error_response = {
                "request_id": request_data_3["request_id"],
                "result": {},
                "info": {
                    "status_code": 500,
                    "description": f"音频转录演示失败: {str(e)}"
                }
            }
            print("\n=== 回复体3 (演示错误) ===")
            print(json.dumps(error_response, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())