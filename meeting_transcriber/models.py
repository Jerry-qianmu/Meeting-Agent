# -*- coding: utf-8 -*-
"""
数据模型

定义会议转写系统中使用的 Pydantic 数据模型。
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class SpeakerLabel(str, Enum):
    """说话人标记"""
    INTERVIEWER = "interviewer"  # 面试官 / 对方
    SELF = "self"                # 自己
    UNKNOWN = "unknown"          # 未知


class MeetingScene(str, Enum):
    """会议场景"""
    INTERVIEW = "interview"      # 面试
    MEETING = "meeting"          # 普通会议
    CUSTOM = "custom"            # 自定义


class AudioSegment(BaseModel):
    """音频片段"""
    session_id: str                          # 所属会话 ID
    speaker: SpeakerLabel                    # 说话人来源
    timestamp: datetime                      # 录制时间戳
    duration: float                          # 时长（秒）
    sample_rate: int = 16000                 # 采样率
    data_path: Optional[str] = None          # 临时文件路径


class TranscriptSegment(BaseModel):
    """转写片段"""
    session_id: str                          # 所属会话 ID
    speaker: SpeakerLabel                    # 说话人
    timestamp: datetime                      # 录制时间戳
    text: str                                # 识别文本
    language: Optional[str] = None           # 检测到的语言
    audio_duration: float = 0.0              # 对应音频时长
    is_final: bool = True                    # 是否为最终结果（False = 中间结果，用于流式显示）


class Suggestion(BaseModel):
    """实时建议"""
    session_id: str                          # 所属会话 ID
    timestamp: datetime                      # 生成时间戳
    content: str                             # 建议内容
    context_summary: Optional[str] = None    # 触发建议时的上下文摘要


class MeetingSession(BaseModel):
    """会议会话"""
    session_id: str                          # 唯一 ID
    scene: MeetingScene = MeetingScene.INTERVIEW  # 场景
    start_time: Optional[datetime] = None    # 开始时间
    end_time: Optional[datetime] = None      # 结束时间
    is_running: bool = False                 # 是否正在录制
    transcripts: list[TranscriptSegment] = Field(default_factory=list)  # 转写记录
    suggestions: list[Suggestion] = Field(default_factory=list)         # 建议记录
    report_path: Optional[str] = None        # 报告文件路径


class MeetingStartRequest(BaseModel):
    """开始录制请求"""
    scene: MeetingScene = MeetingScene.INTERVIEW
    mic_device_index: Optional[int] = None         # 麦克风设备索引（None 则自动选择）
    loopback_device_index: Optional[int] = None    # Loopback 设备索引（None 则自动选择）
    chunk_duration: Optional[float] = None         # 分段时长覆盖


class MeetingStatusResponse(BaseModel):
    """录制状态响应"""
    session_id: str
    is_running: bool
    scene: str
    start_time: Optional[str] = None
    transcript_count: int = 0
    suggestion_count: int = 0
    elapsed_seconds: float = 0.0
