# -*- coding: utf-8 -*-
"""
桌面弹窗应用

基于 tkinter 的会议实时转写与建议系统 GUI。
启动方式: python -m meeting_transcriber.main --gui
"""

import asyncio
import logging
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime

from meeting_transcriber.config import meeting_config
from meeting_transcriber.models import MeetingScene, SpeakerLabel
from meeting_transcriber.audio.recorder import Recorder
from meeting_transcriber.asr.transcriber import Transcriber
from meeting_transcriber.asr.transcript_merger import TranscriptMerger
from meeting_transcriber.advisor.suggestion_engine import SuggestionEngine
from meeting_transcriber.report.markdown_writer import MarkdownWriter

logger = logging.getLogger(__name__)


class MeetingGUI:
    """会议转写桌面应用"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("会议实时转写系统")
        self.root.geometry("900x650")
        self.root.minsize(750, 500)

        # 核心组件
        self._recorder = Recorder()
        self._transcriber = Transcriber()
        self._suggestion_engine = SuggestionEngine()
        self._merger = TranscriptMerger(
            on_merged_callback=self._on_merged_line,
            on_partial_callback=self._on_partial_line,
        )
        self._partial_tag = "partial"  # 中间结果的 text tag
        self._markdown_writer = MarkdownWriter()
        self._session = None
        self._recording = False
        self._stopping = False  # 防止停止过程中窗口被意外销毁
        self._stopped = False

        # asyncio event loop（运行在后台线程）
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None

        # 计时器
        self._start_time: datetime | None = None
        self._timer_running = False

        # 组件引用（用于回调中安全更新）
        self._transcript_text = None
        self._suggestion_text = None
        self._status_label = None
        self._timer_label = None
        self._start_btn = None
        self._stop_btn = None

        self._setup_ui()
        self._setup_callbacks()

    def _setup_ui(self):
        """构建界面"""
        # ── 顶部：配置区 ──────────────────────────────────────────────
        config_frame = ttk.LabelFrame(self.root, text="配置", padding=8)
        config_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        # 场景选择
        ttk.Label(config_frame, text="场景:").grid(row=0, column=0, padx=(0, 5))
        self._scene_var = tk.StringVar(value="面试")
        scene_combo = ttk.Combobox(
            config_frame, textvariable=self._scene_var,
            values=["面试", "会议"], state="readonly", width=8,
        )
        scene_combo.grid(row=0, column=1, padx=(0, 15))

        # ASR 模式选择
        ttk.Label(config_frame, text="识别模式:").grid(row=0, column=2, padx=(0, 5))
        self._asr_mode_var = tk.StringVar(value="批量(Gradio)")
        asr_mode_combo = ttk.Combobox(
            config_frame, textvariable=self._asr_mode_var,
            values=["批量(Gradio)", "流式(Paraformer)"], state="readonly", width=16,
        )
        asr_mode_combo.grid(row=0, column=3, padx=(0, 15))

        # 麦克风选择
        ttk.Label(config_frame, text="麦克风:").grid(row=0, column=4, padx=(0, 5))
        self._mic_var = tk.StringVar(value="自动选择")
        self._mic_combo = ttk.Combobox(
            config_frame, textvariable=self._mic_var,
            state="readonly", width=25,
        )
        self._mic_combo.grid(row=0, column=5, padx=(0, 15))

        # Loopback 设备选择
        ttk.Label(config_frame, text="系统音频:").grid(row=0, column=6, padx=(0, 5))
        self._loopback_var = tk.StringVar(value="自动选择")
        self._loopback_combo = ttk.Combobox(
            config_frame, textvariable=self._loopback_var,
            state="readonly", width=25,
        )
        self._loopback_combo.grid(row=0, column=7)

        # 第二行：文件名
        ttk.Label(config_frame, text="文件名:").grid(row=1, column=0, padx=(0, 5), pady=(8, 0))
        self._filename_var = tk.StringVar(value="")
        filename_entry = ttk.Entry(config_frame, textvariable=self._filename_var, width=40)
        filename_entry.grid(row=1, column=1, columnspan=3, sticky=tk.W, padx=(0, 15), pady=(8, 0))
        ttk.Label(config_frame, text="(留空则自动命名)", foreground="gray").grid(row=1, column=4, columnspan=2, sticky=tk.W, pady=(8, 0))

        # 加载设备列表
        self._load_devices()

        # ── 中部：内容区（左=转写，右=建议）──────────────────────────
        content_frame = ttk.Frame(self.root)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左侧：转写记录
        left_frame = ttk.LabelFrame(content_frame, text="实时转写", padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))

        self._transcript_text = scrolledtext.ScrolledText(
            left_frame, wrap=tk.WORD, font=("Microsoft YaHei", 10),
            state=tk.DISABLED, height=20,
        )
        self._transcript_text.pack(fill=tk.BOTH, expand=True)

        # 右侧：建议
        right_frame = ttk.LabelFrame(content_frame, text="💡 实时建议", padding=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(3, 0))

        self._suggestion_text = scrolledtext.ScrolledText(
            right_frame, wrap=tk.WORD, font=("Microsoft YaHei", 10),
            state=tk.DISABLED, height=20, bg="#FFFDE7",
        )
        self._suggestion_text.pack(fill=tk.BOTH, expand=True)

        # ── 底部：控制区 ──────────────────────────────────────────────
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        self._start_btn = ttk.Button(
            bottom_frame, text="▶ 开始录制", command=self._on_start,
        )
        self._start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self._stop_btn = ttk.Button(
            bottom_frame, text="⏹ 停止录制", command=self._on_stop, state=tk.DISABLED,
        )
        self._stop_btn.pack(side=tk.LEFT, padx=(0, 10))

        self._timer_label = ttk.Label(bottom_frame, text="已录制: 00:00:00", font=("Consolas", 11))
        self._timer_label.pack(side=tk.LEFT, padx=20)

        self._status_label = ttk.Label(bottom_frame, text="就绪", foreground="gray")
        self._status_label.pack(side=tk.RIGHT)

    def _load_devices(self):
        """加载音频设备列表"""
        try:
            from meeting_transcriber.audio.device_manager import get_device_manager
            dm = get_device_manager()

            mics = dm.get_microphone_devices()
            self._mic_devices = {f"{d.name}": d.index for d in mics}
            self._mic_combo["values"] = ["自动选择"] + list(self._mic_devices.keys())

            loopbacks = dm.get_loopback_devices()
            self._loopback_devices = {f"{d.name}": d.index for d in loopbacks}
            self._loopback_combo["values"] = ["自动选择"] + list(self._loopback_devices.keys())

            if not loopbacks:
                messagebox.showwarning("警告", "未找到 WASAPI Loopback 设备。\n请确认已连接音频输出设备（耳机/音箱）。")

        except Exception as e:
            logger.error(f"加载设备失败: {e}")
            messagebox.showerror("错误", f"加载音频设备失败:\n{e}")

    def _setup_callbacks(self):
        """连接核心组件回调到 GUI 更新"""
        self._recorder.set_segment_callback(self._on_audio_segment)
        self._transcriber.set_transcript_callback(self._on_transcript)
        self._suggestion_engine.set_suggestion_callback(self._on_suggestion)

    # ── 回调函数（从线程安全调度到主线程）─────────────────────────────

    def _on_audio_segment(self, segment):
        """音频分段回调 → 交给 ASR"""
        # 流式模式下不走 batch ASR（流式 ASR 通过 _on_stream_frame 直接推送 PCM）
        if meeting_config.asr_mode == "streaming":
            return
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._transcriber.process_segment(segment), self._loop,
            )

    def _on_transcript(self, transcript):
        """转写结果回调 → 合并器处理 + 建议引擎 + 报告"""
        # 喂给合并器（中间结果实时更新，最终结果确认段落）
        self._merger.feed(transcript)
        # 传递给建议引擎（只用最终结果）
        if transcript.is_final:
            self._suggestion_engine.add_transcript(transcript)
        # 写入 Markdown 报告（只用最终结果，立即写入不缓冲）
        if transcript.is_final:
            self._markdown_writer.write_transcript(transcript)

    def _on_merged_line(self, line: str):
        """最终文本行 → 线程安全追加到 GUI"""
        self.root.after(0, self._append_transcript, line)

    def _on_partial_line(self, speaker, line: str):
        """中间结果 → 线程安全实时替换当前行（打字效果）"""
        self.root.after(0, self._update_partial_transcript, line)

    def _on_suggestion(self, suggestion):
        """建议回调 → 更新界面 + 写入报告"""
        time_str = suggestion.timestamp.strftime("%H:%M:%S")
        line = f"[{time_str}] {suggestion.content}\n{'─' * 40}\n"
        self.root.after(0, self._append_suggestion, line)
        self._markdown_writer.write_suggestion(suggestion)

    def _append_transcript(self, line: str):
        """在主线程中追加转写文本"""
        self._transcript_text.config(state=tk.NORMAL)
        self._transcript_text.insert(tk.END, line)
        self._transcript_text.see(tk.END)
        self._transcript_text.config(state=tk.DISABLED)

    def _update_partial_transcript(self, line: str):
        """实时替换最后一行（流式打字效果）"""
        self._transcript_text.config(state=tk.NORMAL)
        # 删除最后一行（如果有）
        last_line_start = self._transcript_text.index("end-2l")
        last_line_end = self._transcript_text.index("end-1c")
        if last_line_start != "1.0" or self._transcript_text.get("1.0", "end-1c"):
            self._transcript_text.delete(last_line_start, last_line_end)
        # 插入新的中间结果（带颜色区分）
        self._transcript_text.insert(tk.END, line + "\n", self._partial_tag)
        # 配置中间结果样式（灰色斜体）
        self._transcript_text.tag_configure(self._partial_tag, foreground="#888888")
        self._transcript_text.see(tk.END)
        self._transcript_text.config(state=tk.DISABLED)

    def _append_suggestion(self, line: str):
        """在主线程中追加建议"""
        self._suggestion_text.config(state=tk.NORMAL)
        self._suggestion_text.insert(tk.END, line)
        self._suggestion_text.see(tk.END)
        self._suggestion_text.config(state=tk.DISABLED)

    # ── 按钮事件 ─────────────────────────────────────────────────────

    def _on_start(self):
        """开始录制"""
        if self._recording:
            return

        # 解析场景
        scene_map = {"面试": MeetingScene.INTERVIEW, "会议": MeetingScene.MEETING}
        scene = scene_map.get(self._scene_var.get(), MeetingScene.INTERVIEW)

        # 解析设备
        mic_index = self._mic_devices.get(self._mic_var.get()) if self._mic_var.get() != "自动选择" else None
        loopback_index = self._loopback_devices.get(self._loopback_var.get()) if self._loopback_var.get() != "自动选择" else None

        try:
            # 启动 asyncio 事件循环（后台线程）
            self._loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._loop_thread.start()

            # 设置建议引擎场景
            self._suggestion_engine.set_scene(scene)
            self._suggestion_engine.clear()

            # 解析 ASR 模式（必须在 recorder.start() 之前设置，因为 start 内部会读取此配置）
            asr_mode = "streaming" if "流式" in self._asr_mode_var.get() else "batch"
            from meeting_transcriber.config import meeting_config
            meeting_config.asr_mode = asr_mode

            # 启动录制
            self._session = self._recorder.start(
                scene=scene,
                mic_device_index=mic_index,
                loopback_device_index=loopback_index,
            )

            # 流式模式：启动流式 ASR
            if asr_mode == "streaming":
                self._recorder.set_transcriber(self._transcriber)
                self._transcriber.start_streaming(self._session.session_id)
                self._status_label.config(text="录制中... (流式ASR)", foreground="green")
            else:
                self._status_label.config(text="录制中... (批量ASR)", foreground="green")

            # 启动报告
            custom_name = self._filename_var.get().strip() or None
            self._markdown_writer.start(self._session, custom_name=custom_name)

            self._recording = True
            self._start_time = datetime.now()

            # 更新 UI 状态
            self._start_btn.config(state=tk.DISABLED)
            self._stop_btn.config(state=tk.NORMAL)
            self._status_label.config(text="录制中...", foreground="green")

            # 清空文本区
            self._transcript_text.config(state=tk.NORMAL)
            self._transcript_text.delete("1.0", tk.END)
            self._transcript_text.config(state=tk.DISABLED)
            self._suggestion_text.config(state=tk.NORMAL)
            self._suggestion_text.delete("1.0", tk.END)
            self._suggestion_text.config(state=tk.DISABLED)
            self._merger.clear()

            # 启动计时器
            self._timer_running = True
            self._update_timer()

            logger.info(f"GUI: 录制已开始 - {scene.value}")

        except Exception as e:
            messagebox.showerror("启动失败", f"无法开始录制:\n{e}")
            logger.error(f"GUI: 启动失败: {e}")

    def _on_stop(self, from_close=False):
        """停止录制 — 立即更新 UI，耗时清理放到后台线程"""
        if not self._recording:
            return

        logger.info("GUI: _on_stop 开始执行")
        self._recording = False
        self._stopping = True
        self._timer_running = False

        # 立即更新 UI（不阻塞主循环）
        self._start_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.DISABLED)
        self._status_label.config(text="正在停止...", foreground="orange")

        # 耗时清理放到后台线程
        t = threading.Thread(target=self._stop_worker, daemon=True)
        t.start()

    def _stop_worker(self):
        """后台线程执行耗时的停止清理工作"""
        try:
            # 1. 停止录音（含等待线程退出）
            logger.info("GUI: 正在停止录音...")
            session = self._recorder.stop()
            logger.info(f"GUI: 录音已停止, session={session}")

            # 2. 等待所有待处理的 ASR 任务完成（最多 15 秒）
            logger.info("GUI: 等待 ASR 处理完成...")
            if self._loop and self._loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._transcriber.wait_pending(), self._loop
                )
                future.result(timeout=15)
            logger.info("GUI: ASR 处理完成")

            # 3. flush 合并器 + 写入报告
            logger.info("GUI: 正在 flush 合并器...")
            self._merger.flush()
            if session:
                logger.info("GUI: 正在写入报告...")
                self._markdown_writer.finish(session)
            logger.info("GUI: 报告写入完成")

            report_path = session.report_path if session else "未知"
            logger.info(f"GUI: 录制已停止, 报告: {report_path}")

            # 4. 回到主线程更新 UI
            self.root.after(0, self._stop_done, report_path, None)

        except Exception as e:
            logger.error(f"GUI: 停止失败: {e}", exc_info=True)
            self.root.after(0, self._stop_done, None, str(e))

    def _stop_done(self, report_path, error):
        """回到主线程完成 UI 更新"""
        self._stopping = False
        if error:
            self._status_label.config(text=f"❌ 停止失败: {error}", foreground="red")
            self._start_btn.config(state=tk.NORMAL)
        else:
            self._start_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)
            self._stop_report_path = report_path
            self._status_label.config(
                text=f"✅ 录制完成 - 报告: {report_path}", foreground="green",
            )
        logger.info("GUI: _on_stop 执行完毕")

    def _show_stop_dialog(self):
        """停止后在状态栏显示结果（不用 messagebox，避免窗口被销毁）"""
        if not hasattr(self, '_stop_report_path'):
            return
        self._status_label.config(
            text=f"✅ 录制完成 - 报告: {self._stop_report_path}",
            foreground="green",
        )

    def _run_loop(self):
        """在后台线程中运行 asyncio event loop"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _update_timer(self):
        """更新计时器显示"""
        if not self._timer_running or not self._start_time:
            return
        elapsed = (datetime.now() - self._start_time).total_seconds()
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        self._timer_label.config(text=f"已录制: {hours:02d}:{minutes:02d}:{seconds:02d}")
        self.root.after(1000, self._update_timer)

    def run(self):
        """启动 GUI 主循环"""
        import types
        _original_destroy = self.root.destroy

        def _tracked_destroy():
            import traceback
            logger.error(f"GUI: root.destroy() 被调用！调用栈:\n{''.join(traceback.format_stack())}")
            _original_destroy()

        self.root.destroy = _tracked_destroy
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        """关闭窗口"""
        import traceback
        logger.info(f"GUI: _on_close 被调用, _recording={self._recording}, _stopping={self._stopping}")
        logger.info(f"GUI: _on_close 调用栈:\n{''.join(traceback.format_stack())}")

        # 如果正在停止录制，忽略关闭请求，等待停止完成
        if self._stopping:
            return

        if self._recording:
            if messagebox.askyesno("确认", "录制正在进行中，确定要关闭吗？"):
                self._on_stop()
            else:
                return

        # 停止 asyncio loop（仅在关闭窗口时）
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("GUI: root.destroy() 即将执行")
        self.root.destroy()


def run_gui():
    """启动桌面 GUI"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("启动桌面 GUI...")
    app = MeetingGUI()
    app.run()
