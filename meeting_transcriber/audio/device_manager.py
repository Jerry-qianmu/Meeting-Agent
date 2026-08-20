# -*- coding: utf-8 -*-
"""
音频设备管理器

枚举 Windows 音频设备，区分 WASAPI Loopback 和麦克风设备。
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AudioDeviceInfo:
    """音频设备信息"""
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    sample_rate: float
    is_loopback: bool = False  # 是否为 WASAPI Loopback 设备
    is_input: bool = False     # 是否为输入（麦克风）设备


class DeviceManager:
    """音频设备管理器"""

    def __init__(self):
        self._devices: list[AudioDeviceInfo] = []
        self._refresh()

    def _refresh(self):
        """刷新设备列表"""
        self._devices.clear()
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            logger.warning("pyaudiowpatch 未安装，尝试使用 pyaudio")
            try:
                import pyaudio
            except ImportError:
                logger.error("pyaudio 和 pyaudiowpatch 均未安装")
                return

        p = pyaudio.PyAudio()
        try:
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                name = info.get("name", "")
                is_loopback = "loopback" in name.lower()
                is_input = info.get("maxInputChannels", 0) > 0
                is_output = info.get("maxOutputChannels", 0) > 0

                device = AudioDeviceInfo(
                    index=i,
                    name=name,
                    max_input_channels=info.get("maxInputChannels", 0),
                    max_output_channels=info.get("maxOutputChannels", 0),
                    sample_rate=info.get("defaultSampleRate", 16000),
                    is_loopback=is_loopback,
                    is_input=is_input and not is_loopback,
                )
                self._devices.append(device)
        finally:
            p.terminate()

        logger.info(f"发现 {len(self._devices)} 个音频设备")

    def list_devices(self) -> list[AudioDeviceInfo]:
        """列出所有设备"""
        return self._devices.copy()

    def get_loopback_devices(self) -> list[AudioDeviceInfo]:
        """获取所有 WASAPI Loopback 设备"""
        return [d for d in self._devices if d.is_loopback]

    def get_microphone_devices(self) -> list[AudioDeviceInfo]:
        """获取所有麦克风（输入）设备"""
        return [d for d in self._devices if d.is_input]

    def auto_select_loopback(self) -> AudioDeviceInfo | None:
        """自动选择 Loopback 设备（优先默认输出设备的 loopback）"""
        loopbacks = self.get_loopback_devices()
        if not loopbacks:
            logger.warning("未找到 WASAPI Loopback 设备")
            return None
        # 优先选择包含 "立体声" 或 "Stereo" 的设备
        for lb in loopbacks:
            if "立体声" in lb.name or "stereo" in lb.name.lower():
                return lb
        return loopbacks[0]

    def auto_select_microphone(self) -> AudioDeviceInfo | None:
        """自动选择麦克风设备

        优先级：
        1. 跳过 Windows 虚拟设备（Microsoft 声音映射器 / Sound Mapper）
        2. 优先选择包含常见物理麦克风关键词的设备
        3. 否则选第一个物理麦克风
        """
        mics = self.get_microphone_devices()
        if not mics:
            logger.warning("未找到麦克风设备")
            return None

        # 过滤掉 Windows 虚拟音频设备
        virtual_keywords = ("声音映射器", "sound mapper", "microsoft default")
        physical_mics = [
            m for m in mics
            if not any(kw in m.name.lower() for kw in virtual_keywords)
        ]

        if not physical_mics:
            logger.warning("未找到物理麦克风设备，使用默认设备")
            return mics[0]

        # 优先选择常见物理麦克风关键词
        preferred_keywords = ("立体声", "stereo", "realtek", "usb", "headset", "earphone", "blue", "hyperx", "razer")
        for mic in physical_mics:
            if any(kw in mic.name.lower() for kw in preferred_keywords):
                logger.info(f"自动选择麦克风: {mic.name}")
                return mic

        logger.info(f"自动选择麦克风: {physical_mics[0].name}")
        return physical_mics[0]

    def get_device_by_index(self, index: int) -> AudioDeviceInfo | None:
        """根据索引获取设备"""
        for d in self._devices:
            if d.index == index:
                return d
        return None


# 全局单例
_device_manager: DeviceManager | None = None


def get_device_manager() -> DeviceManager:
    """获取设备管理器单例"""
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager
