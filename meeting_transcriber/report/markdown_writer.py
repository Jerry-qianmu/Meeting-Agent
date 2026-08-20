# -*- coding: utf-8 -*-
"""
Markdown 报告生成器

实时追加写入转写记录，会议结束后生成完整报告。
"""

import logging
from datetime import datetime
from pathlib import Path

from ..models import TranscriptSegment, Suggestion, MeetingSession, SpeakerLabel
from ..config import meeting_config

logger = logging.getLogger(__name__)


class MarkdownWriter:
    """Markdown 报告生成器"""

    def __init__(self):
        self._session: MeetingSession | None = None
        self._file_path: Path | None = None
        self._file_handle = None

    def start(self, session: MeetingSession, custom_name: str | None = None):
        """开始新报告"""
        self._session = session

        output_dir = Path(meeting_config.report_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if custom_name:
            # 自定义文件名（去掉可能的扩展名）
            name = custom_name.replace(".md", "").replace(".MD", "")
            filename = f"{name}.md"
        else:
            timestamp_str = session.start_time.strftime("%Y%m%d_%H%M%S") if session.start_time else "unknown"
            filename = f"meeting_{session.session_id}_{timestamp_str}.md"
        self._file_path = output_dir / filename

        # 写入文件头
        scene_name = {"interview": "面试", "meeting": "会议", "custom": "自定义"}.get(session.scene.value, "会议")
        start_time_str = session.start_time.strftime("%Y-%m-%d %H:%M:%S") if session.start_time else "未知"

        header = f"""# {scene_name}记录 - {start_time_str}

**会话 ID:** {session.session_id}
**场景:** {scene_name}
**开始时间:** {start_time_str}

---

## 对话记录

"""
        self._write(header)
        logger.info(f"报告已创建: {self._file_path}")

    def write_transcript(self, segment: TranscriptSegment):
        """追加写入转写片段"""
        time_str = segment.timestamp.strftime("%H:%M:%S")
        speaker_name = "面试官" if segment.speaker == SpeakerLabel.INTERVIEWER else "我"
        line = f"**[{time_str}] {speaker_name}：** {segment.text}\n\n"
        self._write(line)
        logger.info(f"[MD] 写入转写: {speaker_name}: {segment.text[:50]}...")

    def write_suggestion(self, suggestion: Suggestion):
        """追加写入建议"""
        time_str = suggestion.timestamp.strftime("%H:%M:%S")
        line = f"> 💡 **建议 [{time_str}]**：{suggestion.content}\n\n"
        self._write(line)

    def finish(self, session: MeetingSession):
        """生成完整报告（会议结束时调用）"""
        if not self._file_path:
            return

        end_time_str = session.end_time.strftime("%Y-%m-%d %H:%M:%S") if session.end_time else "未知"
        duration = ""
        if session.start_time and session.end_time:
            delta = session.end_time - session.start_time
            minutes = int(delta.total_seconds() // 60)
            seconds = int(delta.total_seconds() % 60)
            duration = f"{minutes} 分 {seconds} 秒"

        footer = f"""---

## 会议信息

- **结束时间:** {end_time_str}
- **持续时长:** {duration}
- **转写片段数:** {len(session.transcripts)}
- **建议数:** {len(session.suggestions)}

---
*报告由 Meeting Transcriber 自动生成*
"""
        self._write(footer)
        self._close()

        session.report_path = str(self._file_path)
        logger.info(f"报告已生成: {self._file_path}")

    def _write(self, content: str):
        """写入内容"""
        if self._file_path:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(content)

    def _close(self):
        """关闭文件"""
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None
