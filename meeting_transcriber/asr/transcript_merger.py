# -*- coding: utf-8 -*-
"""
转写文本合并器 — 支持流式中间结果

策略：
- 中间结果（is_final=False）：实时替换当前行（打字效果）
- 最终结果（is_final=False→True）：确认并追加到已输出段落
- 说话人切换：输出新段

只影响显示，不影响建议引擎和报告（它们接收原始分段）。
"""

import logging

from ..models import TranscriptSegment, SpeakerLabel

logger = logging.getLogger(__name__)

MERGE_MAX_CHARS = 500


class TranscriptMerger:
    """转写文本合并器 — 流式"""

    def __init__(self, on_merged_callback=None, on_partial_callback=None):
        """
        Args:
            on_merged_callback: 最终文本行回调 (line: str) → 追加到显示
            on_partial_callback: 中间结果回调 (speaker, text) → 实时替换当前行
        """
        self._on_merged_callback = on_merged_callback
        self._on_partial_callback = on_partial_callback
        self._committed_text = ""       # 已确认的文本（当前段落）
        self._pending_speaker = None    # 当前段落的说话人
        self._pending_timestamp = None  # 当前段落的起始时间
        self._partial_text = ""         # 当前中间结果文本

    def feed(self, segment: TranscriptSegment):
        """输入一个转写片段"""
        text = segment.text.strip()
        if not text:
            return

        speaker = segment.speaker
        ts = segment.timestamp

        if segment.is_final:
            # 说话人切换：先输出之前积累的文本
            if self._pending_speaker is not None and speaker != self._pending_speaker and self._committed_text:
                self._flush()

            # 最终结果：追加到已确认文本
            self._committed_text += text
            self._partial_text = ""
            self._pending_speaker = speaker
            self._pending_timestamp = ts

            # 超长保护
            if len(self._committed_text) >= MERGE_MAX_CHARS:
                self._flush()

            # 通知 UI 更新（用已确认的完整文本）
            self._notify_committed()

            logger.debug(f"[合并] 最终: {self._committed_text[:50]}...")
        else:
            # 中间结果：说话人切换时先 flush
            if self._pending_speaker is not None and speaker != self._pending_speaker and self._committed_text:
                self._flush()

            # 中间结果：实时显示
            self._partial_text = text
            self._pending_speaker = speaker
            if self._on_partial_callback:
                self._on_partial_callback(speaker, self._committed_text + text)

            logger.debug(f"[合并] 中间: {text[:30]}...")

    def flush(self):
        """强制输出（录制结束时调用）"""
        self._flush()

    def _flush(self):
        """输出当前积累的整段文本"""
        if not self._committed_text or not self._pending_speaker:
            return

        speaker_name = "面试官" if self._pending_speaker == SpeakerLabel.INTERVIEWER else "我"
        time_str = self._pending_timestamp.strftime("%H:%M:%S") if self._pending_timestamp else "??:??:??"
        line = f"[{time_str}] {speaker_name}：{self._committed_text}\n"

        if self._on_merged_callback:
            self._on_merged_callback(line)

        logger.debug(f"[合并] 输出: {line.strip()[:80]}...")

        self._committed_text = ""
        self._pending_speaker = None
        self._pending_timestamp = None
        self._partial_text = ""

    def _notify_committed(self):
        """通知 UI 当前已确认的文本"""
        if not self._pending_speaker:
            return
        speaker_name = "面试官" if self._pending_speaker == SpeakerLabel.INTERVIEWER else "我"
        time_str = self._pending_timestamp.strftime("%H:%M:%S") if self._pending_timestamp else "??:??:??"
        line = f"[{time_str}] {speaker_name}：{self._committed_text}"
        if self._on_partial_callback:
            self._on_partial_callback(self._pending_speaker, line)

    def clear(self):
        """清空状态"""
        self._committed_text = ""
        self._pending_speaker = None
        self._pending_timestamp = None
        self._partial_text = ""
