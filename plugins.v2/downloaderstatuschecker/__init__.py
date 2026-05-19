import time
import subprocess
import os
import requests
from datetime import datetime
from typing import List, Dict, Any, Tuple

from apscheduler.triggers.cron import CronTrigger
from app.plugins import _PluginBase
from app.log import logger
from app.helper.downloader import DownloaderHelper


class DownloaderStatusChecker(_PluginBase):
    """
    下载器状态检测插件
    - 下载器离线后自动启动对应 Windows 程序
    - 配置下载器名称与启动路径的映射
    - 可开关自动启动功能
    """
    # 插件名称
    plugin_name = "下载器状态检测"
    # 插件描述
    plugin_desc = "定时检测下载器在线状态，支持识别到下载器离线后自动启动下载器（Windows）"
    # 插件版本
    plugin_version = "1.0.0"
    plugin_icon = "downloaderstatuschecker.png"
    # 插件作者
    plugin_author = "Tante"
    # 作者URL
    author_url = "https://github.com/Tante2000/MoviePilot-Plugins"
    # 插件顺序
    plugin_order = 1
    # 插件配置项 ID 前缀
    plugin_config_prefix = "downloaderstatuschecker_"
    # 配置项
    _enabled = False
    _onlyonce = False
    _cron = ""
    _selected_downloaders = []
    _notify_online = True
    _notify_offline = True
    _auto_start_enabled = False           # 是否启用自动启动
    _downloader_paths = ""                # 多行文本：名称:路径

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled", False)
            self._onlyonce = config.get("onlyonce", False)
            self._cron = config.get("cron", "*/30 * * * *")
            self._selected_downloaders = config.get("selected_downloaders", [])
            self._notify_online = config.get("notify_online", True)
            self._notify_offline = config.get("notify_offline", True)
            self._auto_start_enabled = config.get("auto_start_enabled", False)
            self._downloader_paths = config.get("downloader_paths", "")

        if self._onlyonce:
            logger.info("下载器状态检测：执行立即运行")
            self._check_downloaders()
            self._onlyonce = False
            self.__update_config()

        if self._enabled:
            self.__update_scheduler()
        else:
            self.__stop_scheduler()

    def get_state(self) -> bool:
        return self._enabled

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        downloader_options = []
        try:
            configs = DownloaderHelper().get_configs().values()
            for cfg in configs:
                if hasattr(cfg, 'name') and cfg.name:
                    downloader_options.append({"title": cfg.name, "value": cfg.name})
        except Exception as e:
            logger.error(f"获取下载器列表失败：{str(e)}")

        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                            'hint': '开启后定时检测下载器状态',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'selected_downloaders',
                                            'label': '检测的下载器',
                                            'multiple': True,
                                            'clearable': True,
                                            'chips': True,
                                            'items': [{"title": config.name, "value": config.name}
                                                      for config in DownloaderHelper().get_configs().values()],
                                            'hint': '选择需要检测的下载器（留空则检测全部）',
                                        }
                                    }
                                ]
                            },                                  
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 5},
                                'content': [
                                    {
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '检测周期 (Cron)',
                                            'placeholder': '*/30 * * * *',
                                            'hint': 'Cron表达式，默认每30分钟检测一次',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify_online',
                                            'label': '发送在线通知',
                                            'hint': '下载器在线时发送通知',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify_offline',
                                            'label': '发送离线通知',
                                            'hint': '下载器离线时发送通知',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                            'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'auto_start_enabled',
                                            'label': '离线自动启动程序',
                                            'hint': '检测到下载器离线时，尝试启动对应的 Windows 程序',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },   
                    # --- 路径映射多行文本框 ---
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'downloader_paths',
                                            'label': '下载器启动路径映射',
                                            'rows': 4,
                                            'placeholder': '下载器名称1:程序路径1\n下载器名称2:程序路径2\n例如：\n辅种:C:\\Program Files\\qBittorrent\\qbittorrent.exe\n下载:D:\\Tools\\qbittorrent.exe',
                                            'hint': '每行一个映射，格式为“下载器名称:程序绝对路径”。离线时根据此配置启动对应程序。',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': 'Cron表达式说明：*/30 * * * * 表示每30分钟执行一次。自动启动仅支持Windows本地程序路径。'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "cron": "*/30 * * * *",
            "selected_downloaders": [],
            "notify_online": True,
            "notify_offline": True,
            "auto_start_enabled": False,
            "downloader_paths": ""
        }

    def get_page(self) -> List[dict]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._cron:
            return []

        return [{
            "id": "downloader_status_checker",
            "name": "下载器状态检测",
            "trigger": CronTrigger.from_crontab(self._cron),
            "func": self._check_downloaders,
            "kwargs": {}
        }]

    def stop_service(self):
        self.__stop_scheduler()

    # ------------------- 原有检测辅助方法 -------------------
    def _test_downloader_by_instance(self, helper, name):
        """尝试通过下载器实例的 test 方法检测（自动匹配方法名）"""
        method_names = ['get_downloader', 'get', 'get_client', 'get_instance']
        for method in method_names:
            if hasattr(helper, method):
                try:
                    get_func = getattr(helper, method)
                    instance = get_func(name)
                    if instance and hasattr(instance, 'test'):
                        return instance.test()
                except Exception as e:
                    logger.debug(f"尝试 {method} 失败：{e}")
                    continue
        return False, "无法获取下载器实例"

    def _test_downloader_http(self, host_url):
        """通过 HTTP 请求检测 Web UI 是否可达"""
        try:
            resp = requests.get(f"{host_url.rstrip('/')}/api/v2/app/version", timeout=5)
            if resp.status_code == 200:
                return True, "HTTP 连接成功"
            else:
                return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    # ------------------- 新增：解析路径映射 -------------------
    def _parse_path_mapping(self):
        """
        解析多行文本框中的映射配置，返回字典 {name: path}
        格式：下载器名称:程序路径
        """
        mapping = {}
        if not self._downloader_paths:
            return mapping

        for line in self._downloader_paths.splitlines():
            line = line.strip()
            if not line or ':' not in line:
                continue
            # 只分割第一个冒号，因为 Windows 路径可能包含冒号（盘符后的冒号）
            # 但标准写法是“名称:路径”，路径以盘符开头如 C:\... 其中冒号是第二个字符，
            # 所以用 split(':', 1) 分割一次即可
            parts = line.split(':', 1)
            if len(parts) != 2:
                continue
            name = parts[0].strip()
            path = parts[1].strip()
            if name and path:
                mapping[name] = path
        return mapping

    # ------------------- 新增：自动启动程序 -------------------
    def _start_downloader(self, name, path):
        """尝试启动指定路径的 Windows 程序"""
        if not os.path.exists(path):
            logger.warning(f"自动启动失败：程序路径不存在 - {path}")
            return False, "程序文件不存在"

        try:
            # 使用 subprocess.Popen 非阻塞启动，不等待进程结束
            subprocess.Popen(
                path,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info(f"已尝试启动下载器 [{name}]，程序路径：{path}")
            return True, "启动命令已发送"
        except Exception as e:
            logger.error(f"启动下载器 [{name}] 失败：{str(e)}")
            return False, str(e)

    # ------------------- 核心检测逻辑（含自动启动） -------------------
    def _check_downloaders(self):
        logger.info("开始检测下载器状态...")

        try:
            helper = DownloaderHelper()
            configs = helper.get_configs().values()
            if not configs:
                logger.warning("未找到任何下载器模块")
                self.post_message(
                    title="【下载器状态检测】",
                    text="未找到任何已配置的下载器"
                )
                return

            online_list = []
            offline_list = []

            for cfg in configs:
                name = cfg.name if hasattr(cfg, 'name') else None
                if not name:
                    continue
                if self._selected_downloaders and name not in self._selected_downloaders:
                    continue

                result, message = False, "未知错误"
                try:
                    result, message = self._test_downloader_by_instance(helper, name)
                    if not result and hasattr(cfg, 'config') and cfg.config.get('host'):
                        host = cfg.config['host']
                        logger.debug(f"下载器 [{name}] 实例检测失败，尝试 HTTP 检测：{host}")
                        result, message = self._test_downloader_http(host)
                except Exception as e:
                    logger.error(f"检测下载器 [{name}] 时出错：{str(e)}")
                    message = f"检测异常：{str(e)}"

                if result:
                    logger.info(f"下载器 [{name}] 在线")
                    online_list.append(name)
                else:
                    logger.warning(f"下载器 [{name}] 离线 - {message}")
                    offline_list.append(name)

                    # ---- 自动启动处理 ----
                    if self._auto_start_enabled:
                        path_map = self._parse_path_mapping()
                        exe_path = path_map.get(name)
                        if exe_path:
                            ok, start_msg = self._start_downloader(name, exe_path)
                            # 发送通知
                            self.post_message(
                                title=f"已尝试启动下载器 [{name}]",
                                text=f"程序路径：{exe_path}"
                            )
                            if not ok:
                                offline_list[-1] += f" (自动启动失败: {start_msg})"
                                # 发送通知
                                self.post_message(
                                title=f" (自动启动失败: {start_msg})"
                            )
                        else:
                            logger.debug(f"下载器 [{name}] 未配置启动路径，跳过自动启动")
                             # 发送通知
                            self.post_message(
                                title=f"下载器 [{name}] 未配置启动路径，跳过自动启动"
                            )

            # 发送通知
            if online_list and self._notify_online:
                status_text = "\n".join([f"✅ {n}" for n in online_list])
                self.post_message(
                    title=f"【下载器状态检测】在线 ({len(online_list)}个)",
                    text=f"检测时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{status_text}"
                )
            if offline_list and self._notify_offline:
                status_text = "\n".join([f"❌ {n}" for n in offline_list])
                self.post_message(
                    title=f"【下载器状态检测】离线 ({len(offline_list)}个)",
                    text=f"检测时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{status_text}"
                )

        except Exception as e:
            logger.error(f"下载器状态检测失败：{str(e)}")
            self.post_message(
                title="【下载器状态检测】异常",
                text=f"检测过程发生异常：{str(e)}"
            )

    def __update_scheduler(self):
        self.__stop_scheduler()
        if self._enabled and self._cron:
            try:
                CronTrigger.from_crontab(self._cron)
                from app.scheduler import Scheduler
                scheduler = Scheduler.get_instance()
                scheduler.add_job(
                    func=self._check_downloaders,
                    trigger=CronTrigger.from_crontab(self._cron),
                    job_id="downloader_status_checker",
                    name="下载器状态检测"
                )
                logger.info(f"下载器状态检测任务已调度：cron={self._cron}")
            except Exception as e:
                logger.error(f"启动调度任务失败：{str(e)}")

    def __stop_scheduler(self):
        try:
            from app.scheduler import Scheduler
            scheduler = Scheduler.get_instance()
            if scheduler:
                scheduler.remove_job("downloader_status_checker")
                logger.info("下载器状态检测任务已停止")
        except Exception as e:
            logger.debug(f"停止调度任务失败（可能任务不存在）：{str(e)}")

    def __update_config(self):
        self.update_config({
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "selected_downloaders": self._selected_downloaders,
            "notify_online": self._notify_online,
            "notify_offline": self._notify_offline,
            "auto_start_enabled": self._auto_start_enabled,
            "downloader_paths": self._downloader_paths
        })

    def get_api(self):
        return {}