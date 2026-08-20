# -*- coding: utf-8 -*-
"""
音频捕获诊断脚本

测试项目：
1. 设备枚举
2. 麦克风录音（普通模式）
3. Loopback 录音（普通模式）
4. 双流同时录音（麦克风 + Loopback）
5. 流式模式测试
6. ASR 识别测试
"""

import os
import sys
import wave
import tempfile
import time
import threading

cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, parent_dir)


def get_pyaudio():
    """获取 pyaudio 模块"""
    try:
        import pyaudiowpatch as pyaudio
        return pyaudio
    except ImportError:
        import pyaudio
        return pyaudio


# ═══════════════════════════════════════════════════════════════════
#  步骤 1：列出所有音频设备
# ═══════════════════════════════════════════════════════════════════
def step1_list_devices():
    print("=" * 60)
    print("步骤1：列出所有音频设备")
    print("=" * 60)

    pyaudio = get_pyaudio()
    p = pyaudio.PyAudio()
    device_count = p.get_device_count()
    print(f"\n共发现 {device_count} 个音频设备:\n")

    loopback_devices = []
    mic_devices = []

    for i in range(device_count):
        info = p.get_device_info_by_index(i)
        name = info.get("name", "")
        in_ch = info.get("maxInputChannels", 0)
        out_ch = info.get("maxOutputChannels", 0)
        rate = info.get("defaultSampleRate", 0)
        is_loopback = "loopback" in name.lower()

        tag = ""
        if is_loopback:
            tag = " ★ [LOOPBACK]"
            loopback_devices.append((i, name, rate))
        elif in_ch > 0:
            tag = " ★ [MIC]"
            mic_devices.append((i, name, rate))

        print(f"  [{i:2d}] {name}")
        print(f"       输入通道={in_ch}, 输出通道={out_ch}, 采样率={rate:.0f}{tag}")

    p.terminate()

    print(f"\n--- 发现 {len(loopback_devices)} 个 Loopback 设备 ---")
    for idx, name, rate in loopback_devices:
        print(f"  [{idx}] {name} ({rate:.0f}Hz)")

    print(f"\n--- 发现 {len(mic_devices)} 个麦克风设备 ---")
    for idx, name, rate in mic_devices:
        print(f"  [{idx}] {name} ({rate:.0f}Hz)")

    return loopback_devices, mic_devices


# ═══════════════════════════════════════════════════════════════════
#  步骤 2：测试麦克风录音（普通模式）
# ═══════════════════════════════════════════════════════════════════
def step2_test_microphone(device_index: int, duration: int = 5):
    print("\n" + "=" * 60)
    print(f"步骤2：测试麦克风录音 (设备 [{device_index}], 时长 {duration}秒)")
    print("=" * 60)

    pyaudio = get_pyaudio()
    p = pyaudio.PyAudio()
    try:
        info = p.get_device_info_by_index(device_index)
        print(f"设备: {info['name']}")
        print(f"采样率: {info['defaultSampleRate']:.0f}Hz")
        print(f"最大输入通道: {info['maxInputChannels']}")

        # 使用设备原生参数，避免强制采样率导致静音
        device_rate = int(info['defaultSampleRate'])
        device_channels = max(info.get('maxInputChannels', 1), 1)
        print(f"  使用原生参数: {device_rate}Hz, {device_channels}ch")

        stream = p.open(
            format=pyaudio.paInt16,
            channels=device_channels,
            rate=device_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=1024,
        )

        print(f"\n>>> 请对着麦克风说话 ({duration}秒)... <<<")
        frames = []
        for i in range(0, int(device_rate / 1024 * duration)):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)

        stream.stop_stream()
        stream.close()

        raw = b"".join(frames)
        max_amplitude = max(abs(int.from_bytes(raw[i:i+2], byteorder='little', signed=True))
                          for i in range(0, len(raw), 2))

        print(f"\n录音完成，最大振幅: {max_amplitude}")

        if max_amplitude < 100:
            print("[WARNING] 振幅极低，麦克风可能没有拾到声音")
        else:
            print("[OK] 麦克风录音正常")

        # 多声道转单声道 + 重采样到 16000Hz
        import numpy as np
        audio = np.frombuffer(raw, dtype=np.int16)
        if device_channels > 1:
            audio = audio.reshape(-1, device_channels).mean(axis=1).astype(np.int16)
            print(f"  已转换: {device_channels}ch → 1ch")
        if device_rate != 16000:
            ratio = 16000 / device_rate
            new_length = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, new_length).astype(int)
            audio = audio[indices].astype(np.int16)
            print(f"  已重采样: {device_rate}Hz → 16000Hz")

        tmp_path = os.path.join(tempfile.gettempdir(), "test_mic.wav")
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.tobytes())
        print(f"WAV 已保存: {tmp_path}")
        return tmp_path

    except Exception as e:
        print(f"[FAIL] 麦克风录音失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        p.terminate()


# ═══════════════════════════════════════════════════════════════════
#  步骤 3：测试 Loopback 录音（普通模式）
# ═══════════════════════════════════════════════════════════════════
def step3_test_loopback(device_index: int, duration: int = 5):
    print("\n" + "=" * 60)
    print(f"步骤3：测试 Loopback 录音 (设备 [{device_index}], 时长 {duration}秒)")
    print("=" * 60)

    pyaudio = get_pyaudio()
    p = pyaudio.PyAudio()
    try:
        info = p.get_device_info_by_index(device_index)
        print(f"设备: {info['name']}")
        print(f"采样率: {info['defaultSampleRate']:.0f}Hz")
        print(f"最大输入通道: {info['maxInputChannels']}")

        device_rate = int(info['defaultSampleRate'])
        device_channels = max(info.get('maxInputChannels', 2), 2)

        print(f"  使用原生参数: {device_rate}Hz, {device_channels}ch")

        stream = p.open(
            format=pyaudio.paInt16,
            channels=device_channels,
            rate=device_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=1024,
        )

        print(f"\n>>> 请播放一段音频（音乐/视频/说话）({duration}秒)... <<<")

        frames = []
        for i in range(0, int(device_rate / 1024 * duration)):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)

        stream.stop_stream()
        stream.close()

        raw = b"".join(frames)
        max_amplitude = max(abs(int.from_bytes(raw[i:i+2], byteorder='little', signed=True))
                          for i in range(0, len(raw), 2))

        print(f"\n录音完成，最大振幅: {max_amplitude}")

        if max_amplitude < 100:
            print("[WARNING] 振幅极低，Loopback 可能没有拾到系统音频")
        else:
            print("[OK] Loopback 录音正常")

        import numpy as np
        audio = np.frombuffer(raw, dtype=np.int16)

        if device_channels > 1:
            audio = audio.reshape(-1, device_channels).mean(axis=1).astype(np.int16)
            print(f"  已转换: {device_channels}ch → 1ch (单声道)")

        if device_rate != 16000:
            ratio = 16000 / device_rate
            new_length = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, new_length).astype(int)
            audio = audio[indices].astype(np.int16)
            print(f"  已重采样: {device_rate}Hz → 16000Hz")

        tmp_path = os.path.join(tempfile.gettempdir(), "test_loopback.wav")
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.tobytes())
        print(f"WAV 已保存: {tmp_path}")
        return tmp_path

    except Exception as e:
        print(f"[FAIL] Loopback 录音失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        p.terminate()


# ═══════════════════════════════════════════════════════════════════
#  步骤 4：测试双流同时录音
# ═══════════════════════════════════════════════════════════════════
def step4_test_dual_stream(mic_index: int, loopback_index: int, duration: int = 5):
    print("\n" + "=" * 60)
    print(f"步骤4：测试双流同时录音 (麦克风 [{mic_index}] + Loopback [{loopback_index}], {duration}秒)")
    print("=" * 60)

    pyaudio = get_pyaudio()
    p = pyaudio.PyAudio()
    mic_frames = []
    loopback_frames = []
    errors = {"mic": None, "loopback": None}

    try:
        # 打开麦克风（使用原生参数）
        mic_info = p.get_device_info_by_index(mic_index)
        mic_rate = int(mic_info['defaultSampleRate'])
        mic_ch = max(mic_info.get('maxInputChannels', 1), 1)
        print(f"麦克风: {mic_info['name']} ({mic_rate}Hz, {mic_ch}ch)")

        mic_stream = p.open(
            format=pyaudio.paInt16,
            channels=mic_ch,
            rate=mic_rate,
            input=True,
            input_device_index=mic_index,
            frames_per_buffer=1024,
        )

        # 打开 Loopback
        lb_info = p.get_device_info_by_index(loopback_index)
        lb_rate = int(lb_info['defaultSampleRate'])
        lb_ch = max(lb_info.get('maxInputChannels', 2), 2)
        print(f"Loopback: {lb_info['name']} ({lb_rate}Hz, {lb_ch}ch)")

        lb_stream = p.open(
            format=pyaudio.paInt16,
            channels=lb_ch,
            rate=lb_rate,
            input=True,
            input_device_index=loopback_index,
            frames_per_buffer=1024,
        )

        print(f"\n>>> 双流录音开始 ({duration}秒)... <<<")
        print(">>> 请同时对着麦克风说话，并播放一段音频 <<<")

        # 用线程同时读取
        stop_event = threading.Event()

        def read_mic():
            try:
                while not stop_event.is_set():
                    data = mic_stream.read(1024, exception_on_overflow=False)
                    mic_frames.append(data)
            except Exception as e:
                errors["mic"] = str(e)

        def read_loopback():
            try:
                while not stop_event.is_set():
                    data = lb_stream.read(1024, exception_on_overflow=False)
                    loopback_frames.append(data)
            except Exception as e:
                errors["loopback"] = str(e)

        t1 = threading.Thread(target=read_mic, daemon=True)
        t2 = threading.Thread(target=read_loopback, daemon=True)
        t1.start()
        t2.start()

        time.sleep(duration)
        stop_event.set()
        t1.join(timeout=2)
        t2.join(timeout=2)

        mic_stream.stop_stream()
        mic_stream.close()
        lb_stream.stop_stream()
        lb_stream.close()

        # 分析麦克风
        if mic_frames:
            raw = b"".join(mic_frames)
            max_amp = max(abs(int.from_bytes(raw[i:i+2], byteorder='little', signed=True))
                         for i in range(0, min(len(raw), 100000), 2))
            print(f"\n麦克风: 最大振幅={max_amp}, 数据量={len(raw)} bytes")
            if errors["mic"]:
                print(f"  错误: {errors['mic']}")
            elif max_amp < 100:
                print("  [WARNING] 振幅极低")
            else:
                print("  [OK] 正常")

            mic_path = os.path.join(tempfile.gettempdir(), "test_dual_mic.wav")
            with wave.open(mic_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                # 简单重采样
                import numpy as np
                audio = np.frombuffer(raw, dtype=np.int16)
                if mic_ch > 1:
                    audio = audio.reshape(-1, mic_ch).mean(axis=1).astype(np.int16)
                if mic_rate != 16000:
                    ratio = 16000 / mic_rate
                    new_len = int(len(audio) * ratio)
                    indices = np.linspace(0, len(audio) - 1, new_len).astype(int)
                    audio = audio[indices].astype(np.int16)
                wf.writeframes(audio.tobytes())
            print(f"  WAV: {mic_path}")
        else:
            mic_path = None
            print("\n麦克风: 无数据")

        # 分析 Loopback
        if loopback_frames:
            raw = b"".join(loopback_frames)
            max_amp = max(abs(int.from_bytes(raw[i:i+2], byteorder='little', signed=True))
                         for i in range(0, min(len(raw), 100000), 2))
            print(f"\nLoopback: 最大振幅={max_amp}, 数据量={len(raw)} bytes")
            if errors["loopback"]:
                print(f"  错误: {errors['loopback']}")
            elif max_amp < 100:
                print("  [WARNING] 振幅极低")
            else:
                print("  [OK] 正常")

            lb_path = os.path.join(tempfile.gettempdir(), "test_dual_loopback.wav")
            with wave.open(lb_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                import numpy as np
                audio = np.frombuffer(raw, dtype=np.int16)
                if lb_ch > 1:
                    audio = audio.reshape(-1, lb_ch).mean(axis=1).astype(np.int16)
                if lb_rate != 16000:
                    ratio = 16000 / lb_rate
                    new_len = int(len(audio) * ratio)
                    indices = np.linspace(0, len(audio) - 1, new_len).astype(int)
                    audio = audio[indices].astype(np.int16)
                wf.writeframes(audio.tobytes())
            print(f"  WAV: {lb_path}")
        else:
            lb_path = None
            print("\nLoopback: 无数据")

        print("\n[OK] 双流录音完成")
        return mic_path, lb_path

    except Exception as e:
        print(f"[FAIL] 双流录音失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None
    finally:
        p.terminate()


# ═══════════════════════════════════════════════════════════════════
#  步骤 5：测试 AudioCapture 模块
# ═══════════════════════════════════════════════════════════════════
def step5_test_capture_module(mic_index: int, loopback_index: int = None, duration: int = 8):
    print("\n" + "=" * 60)
    print(f"步骤5：测试 AudioCapture 模块 (麦克风 [{mic_index}]")
    if loopback_index is not None:
        print(f"       + Loopback [{loopback_index}]")
    print(f"       时长 {duration}秒)")
    print("=" * 60)

    try:
        from meeting_transcriber.audio.device_manager import AudioDeviceInfo
        from meeting_transcriber.audio.capture import AudioCapture

        # 构造设备信息
        pyaudio = get_pyaudio()
        p = pyaudio.PyAudio()

        mic_info = p.get_device_info_by_index(mic_index)
        mic_device = AudioDeviceInfo(
            index=mic_index,
            name=mic_info['name'],
            max_input_channels=int(mic_info.get('maxInputChannels', 1)),
            max_output_channels=int(mic_info.get('maxOutputChannels', 0)),
            sample_rate=mic_info['defaultSampleRate'],
            is_loopback=False,
            is_input=True,
        )
        print(f"麦克风设备: [{mic_device.index}] {mic_device.name}")

        loopback_device = None
        if loopback_index is not None:
            lb_info = p.get_device_info_by_index(loopback_index)
            loopback_device = AudioDeviceInfo(
                index=loopback_index,
                name=lb_info['name'],
                max_input_channels=int(lb_info.get('maxInputChannels', 2)),
                max_output_channels=int(lb_info.get('maxOutputChannels', 0)),
                sample_rate=lb_info['defaultSampleRate'],
                is_loopback=True,
                is_input=True,
            )
            print(f"Loopback设备: [{loopback_device.index}] {loopback_device.name}")

        p.terminate()

        # 创建 AudioCapture
        capture = AudioCapture(
            mic_device=mic_device,
            loopback_device=loopback_device,
        )

        # 收集回调数据
        chunk_results = []
        stream_results = {"mic": 0, "loopback": 0}

        def on_chunk(segment):
            chunk_results.append(segment)
            print(f"  [chunk] {segment.speaker.value}: {segment.duration:.1f}s, {segment.data_path}")

        def on_stream(speaker, pcm_data):
            key = "mic" if speaker.value == "self" else "loopback"
            stream_results[key] += len(pcm_data)

        capture.set_chunk_callback(on_chunk)
        capture.set_stream_callback(on_stream)

        print(f"\n>>> AudioCapture 启动 ({duration}秒)... <<<")
        capture.start()
        time.sleep(duration)
        capture.stop()

        # 结果
        print(f"\n--- 结果 ---")
        print(f"收到 {len(chunk_results)} 个音频分段")
        for seg in chunk_results:
            print(f"  {seg.speaker.value}: {seg.duration:.1f}s -> {seg.data_path}")

        print(f"流式数据: mic={stream_results['mic']} bytes, loopback={stream_results['loopback']} bytes")

        if chunk_results:
            print("[OK] AudioCapture 模块正常")
        else:
            print("[WARNING] 未收到任何音频分段")

        if stream_results["mic"] > 0 or stream_results["loopback"] > 0:
            print("[OK] 流式回调正常")
        else:
            print("[WARNING] 流式回调未收到数据")

        return chunk_results

    except Exception as e:
        print(f"[FAIL] AudioCapture 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════
#  步骤 6：测试流式 ASR 模式
# ═══════════════════════════════════════════════════════════════════
def step6_test_streaming_mode(mic_index: int, loopback_index: int = None, duration: int = 10):
    print("\n" + "=" * 60)
    print(f"步骤6：测试流式 ASR 模式 (时长 {duration}秒)")
    print("=" * 60)

    try:
        from meeting_transcriber.audio.device_manager import AudioDeviceInfo
        from meeting_transcriber.audio.capture import AudioCapture
        from meeting_transcriber.asr.streaming_asr import StreamingASRSession
        from meeting_transcriber.models import SpeakerLabel

        pyaudio = get_pyaudio()
        p = pyaudio.PyAudio()

        mic_info = p.get_device_info_by_index(mic_index)
        mic_device = AudioDeviceInfo(
            index=mic_index,
            name=mic_info['name'],
            max_input_channels=int(mic_info.get('maxInputChannels', 1)),
            max_output_channels=int(mic_info.get('maxOutputChannels', 0)),
            sample_rate=mic_info['defaultSampleRate'],
            is_loopback=False,
            is_input=True,
        )

        loopback_device = None
        if loopback_index is not None:
            lb_info = p.get_device_info_by_index(loopback_index)
            loopback_device = AudioDeviceInfo(
                index=loopback_index,
                name=lb_info['name'],
                max_input_channels=int(lb_info.get('maxInputChannels', 2)),
                max_output_channels=int(lb_info.get('maxOutputChannels', 0)),
                sample_rate=lb_info['defaultSampleRate'],
                is_loopback=True,
                is_input=True,
            )

        p.terminate()

        # 检查 API Key
        from meeting_transcriber.config import meeting_config
        if not meeting_config.dashscope_api_key:
            print("[SKIP] DASHSCOPE_API_KEY 未设置，跳过流式 ASR 测试")
            print("  请在 .env 中设置: DASHSCOPE_API_KEY=your_key")
            return

        print(f"DashScope API Key: ...{meeting_config.dashscope_api_key[-6:]}")

        # 创建流式 ASR 会话
        transcripts = []

        def on_transcript(segment):
            transcripts.append(segment)
            print(f"  [ASR] {segment.speaker.value}: {segment.text}")

        mic_asr = StreamingASRSession(
            speaker=SpeakerLabel.SELF,
            on_transcript_callback=on_transcript,
        )
        mic_asr.start()
        print("[OK] 麦克风流式 ASR 会话已启动")

        loopback_asr = None
        if loopback_device:
            loopback_asr = StreamingASRSession(
                speaker=SpeakerLabel.INTERVIEWER,
                on_transcript_callback=on_transcript,
            )
            loopback_asr.start()
            print("[OK] Loopback 流式 ASR 会话已启动")

        # 创建 AudioCapture 并设置流式回调
        capture = AudioCapture(
            mic_device=mic_device,
            loopback_device=loopback_device,
        )

        def on_stream(speaker, pcm_data):
            if speaker == SpeakerLabel.SELF:
                mic_asr.send_audio(pcm_data)
            else:
                if loopback_asr:
                    loopback_asr.send_audio(pcm_data)

        capture.set_stream_callback(on_stream)

        print(f"\n>>> 流式录音+识别开始 ({duration}秒)... <<<")
        print(">>> 请对着麦克风说话 <<<")
        capture.start()
        time.sleep(duration)
        capture.stop()

        # 停止 ASR
        mic_asr.stop()
        if loopback_asr:
            loopback_asr.stop()

        # 结果
        print(f"\n--- 流式 ASR 结果 ---")
        print(f"共识别 {len(transcripts)} 条转写")
        for t in transcripts:
            print(f"  [{t.speaker.value}] {t.text}")

        if transcripts:
            print("[OK] 流式 ASR 工作正常")
        else:
            print("[WARNING] 未识别到任何文本")
            print("  可能原因:")
            print("  1. DASHSCOPE_API_KEY 无效")
            print("  2. 麦克风没有拾到声音")
            print("  3. 网络连接问题")

    except ImportError as e:
        print(f"[FAIL] 缺少依赖: {e}")
        print("  请执行: pip install dashscope")
    except Exception as e:
        print(f"[FAIL] 流式 ASR 测试失败: {e}")
        import traceback
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════
#  步骤 7：ASR 识别测试
# ═══════════════════════════════════════════════════════════════════
def step7_test_asr(audio_path: str, label: str = "音频"):
    print("\n" + "=" * 60)
    print(f"步骤7：测试 ASR 识别 ({label})")
    print("=" * 60)

    if not audio_path:
        print("[SKIP] 无音频文件，跳过 ASR 测试")
        return

    print(f"音频文件: {audio_path}")
    print(f"文件大小: {os.path.getsize(audio_path)} bytes")

    try:
        from gradio_client import Client, handle_file
        from meeting_transcriber.config import meeting_config

        print(f"连接 ASR 服务: {meeting_config.asr_server_url}")
        client = Client(meeting_config.asr_server_url)
        print("ASR 服务连接成功，开始识别...")

        start = time.time()
        result = client.predict(
            audio_upload=handle_file(audio_path),
            lang_disp="Auto",
            api_name="/run",
        )
        elapsed = time.time() - start

        if isinstance(result, (tuple, list)) and len(result) >= 2:
            lang, text = str(result[0]), str(result[1])
        else:
            lang, text = "unknown", str(result)

        print(f"\n识别耗时: {elapsed:.2f}秒")
        print(f"检测语言: {lang}")
        print(f"识别结果: {text}")

        if not text.strip():
            print("[WARNING] 识别结果为空")
        else:
            print("[OK] ASR 识别成功")

    except Exception as e:
        print(f"[FAIL] ASR 识别失败: {e}")
        import traceback
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  音频捕获诊断工具 (增强版)")
    print("=" * 60)
    print()
    print("已知可用配置: 麦克风=1 (K9U PRO), Loopback=38 (耳机 K9U PRO)")
    print()

    # 步骤1：列出设备
    result = step1_list_devices()
    if not result:
        print("\n无法继续，设备枚举失败")
        return

    loopback_devices, mic_devices = result

    # 交互式选择
    print("\n" + "-" * 60)
    print("选择测试模式:")
    print("  1 = 仅麦克风测试")
    print("  2 = 仅 Loopback 测试")
    print("  3 = 双流测试 (麦克风 + Loopback)")
    print("  4 = AudioCapture 模块测试")
    print("  5 = 流式 ASR 测试")
    print("  6 = 全部测试")
    print("  0 = 退出")
    print("-" * 60)

    mode = input("请选择 (默认 3): ").strip() or "3"

    mic_idx = 1
    lb_idx = 38
    duration = 5

    if mic_devices:
        choice = input(f"麦克风编号 (默认 0): ").strip()
        if choice:
            mic_idx = int(choice)

    if loopback_devices:
        choice = input(f"Loopback 编号 (默认 38): ").strip()
        if choice:
            lb_idx = int(choice)

    choice = input("录音时长秒数 (默认 5): ").strip()
    if choice:
        duration = int(choice)

    if mode == "1":
        mic_path = step2_test_microphone(mic_idx, duration)
        step7_test_asr(mic_path, "麦克风")

    elif mode == "2":
        loop_path = step3_test_loopback(lb_idx, duration)
        step7_test_asr(loop_path, "Loopback")

    elif mode == "3":
        mic_path, lb_path = step4_test_dual_stream(mic_idx, lb_idx, duration)
        step7_test_asr(mic_path, "麦克风")
        step7_test_asr(lb_path, "Loopback")

    elif mode == "4":
        step5_test_capture_module(mic_idx, lb_idx, duration)

    elif mode == "5":
        step6_test_streaming_mode(mic_idx, lb_idx, duration + 5)

    elif mode == "6":
        mic_path = step2_test_microphone(mic_idx, duration)
        step7_test_asr(mic_path, "麦克风")

        loop_path = step3_test_loopback(lb_idx, duration)
        step7_test_asr(loop_path, "Loopback")

        mic_path2, lb_path2 = step4_test_dual_stream(mic_idx, lb_idx, duration)

        step5_test_capture_module(mic_idx, lb_idx, duration)

        step6_test_streaming_mode(mic_idx, lb_idx, duration + 5)

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
