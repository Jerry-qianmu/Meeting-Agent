# -*- coding: utf-8 -*-
"""
实时建议引擎

基于 LLM 分析对话上下文，生成面试/会议建议。
"""

import asyncio
import logging
import time
from datetime import datetime

import dashscope
from dashscope import Generation

from ..models import TranscriptSegment, Suggestion, MeetingScene, SpeakerLabel
from ..config import meeting_config
from .prompts import INTERVIEW_SUGGESTION_PROMPT, MEETING_SUGGESTION_PROMPT

logger = logging.getLogger(__name__)


class SuggestionEngine:
    """实时建议引擎"""

    def __init__(self):
        dashscope.api_key = meeting_config.dashscope_api_key
        self._context: list[TranscriptSegment] = []
        self._last_suggestion_time: float = 0
        self._on_suggestion_callback = None
        self._scene: MeetingScene = MeetingScene.INTERVIEW

    def set_scene(self, scene: MeetingScene):
        """设置会议场景"""
        self._scene = scene

    def add_transcript(self, segment: TranscriptSegment):
        """
        添加新的转写片段到上下文，并判断是否需要触发建议。

        Args:
            segment: 转写片段
        """
        self._context.append(segment)

        # 限制上下文窗口大小
        max_rounds = meeting_config.suggestion_context_rounds * 2  # 每轮 = 说话人 + 回答
        if len(self._context) > max_rounds:
            self._context = self._context[-max_rounds:]

        # 检查是否应该触发建议
        if self._should_trigger():
            asyncio.create_task(self._generate_suggestion())

    def _should_trigger(self) -> bool:
        """判断是否应该触发建议生成"""
        if not self._context:
            return False

        now = time.time()
        min_interval = meeting_config.suggestion_min_interval

        # 最小间隔检查
        if now - self._last_suggestion_time < min_interval:
            return False

        # 说话人切换触发：面试官刚说完话（可能是新问题）
        if len(self._context) >= 2:
            last = self._context[-1]
            prev = self._context[-2]
            # 从 self 切换到 interviewer，说明用户回答完毕，新问题来了
            if prev.speaker == SpeakerLabel.SELF and last.speaker == SpeakerLabel.INTERVIEWER:
                return True

        # 时间触发
        if now - self._last_suggestion_time >= meeting_config.suggestion_time_trigger:
            if len(self._context) >= 4:  # 至少有 2 轮对话
                return True

        return False

    async def _generate_suggestion(self):
        """调用 LLM 生成建议"""
        self._last_suggestion_time = time.time()

        try:
            # 构建上下文文本
            context_lines = []
            for seg in self._context[-10:]:  # 最近 10 条
                speaker_name = "面试官" if seg.speaker == SpeakerLabel.INTERVIEWER else "我"
                context_lines.append(f"{speaker_name}：{seg.text}")
            context = "\n".join(context_lines)

            # 选择 prompt
            if self._scene == MeetingScene.INTERVIEW:
                prompt = INTERVIEW_SUGGESTION_PROMPT.format(context=context)
            else:
                prompt = MEETING_SUGGESTION_PROMPT.format(context=context)

            # 调用 LLM
            response = await asyncio.to_thread(
                Generation.call,
                model=meeting_config.suggestion_model,
                messages=[{"role": "user", "content": prompt}],
                result_format="message",
            )

            if response.status_code == 200:
                content = response.output.choices[0].message.content
                suggestion = Suggestion(
                    session_id=self._context[-1].session_id if self._context else "",
                    timestamp=datetime.now(),
                    content=content,
                    context_summary=context[:200],
                )

                if self._on_suggestion_callback:
                    self._on_suggestion_callback(suggestion)

                logger.info(f"建议已生成: {content[:80]}...")
            else:
                logger.error(f"LLM 调用失败: {response.code} - {response.message}")

        except Exception as e:
            logger.error(f"建议生成失败: {e}")

    def clear(self):
        """清空上下文"""
        self._context.clear()
        self._last_suggestion_time = 0

    def set_suggestion_callback(self, callback):
        """设置建议回调"""
        self._on_suggestion_callback = callback
