#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# Ensure project root is in sys.path for script-mode execution
# This allows absolute imports to work even when running as a script
_current_root = Path(__file__).resolve().parent
if str(_current_root) not in sys.path:
    sys.path.insert(0, str(_current_root))


"""
智能启动器 - 玄枢 Agent
功能：
- 自动检测环境问题
- 自动安装依赖
- 检测并自动启动Ollama
- 模型选择（支持Ollama和外部API）
- 友好的用户界面
"""
import os
import sys
import subprocess
import time
import requests
from typing import List, Dict, Optional
from colorama import init, Fore, Style
from config import WEB_HOST, WEB_PORT

init(autoreset=True)


class Launcher:
    """智能启动器"""

    def __init__(self):
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.requirements_file = os.path.join(self.project_root, 'requirements.txt')
        self.config_file = os.path.join(self.project_root, 'config.py')
        self.selected_provider = None

    def print_banner(self):
        """打印启动横幅"""
        print(Fore.CYAN + Style.BRIGHT + r"""
╔═══════════════════════════════════════════════════════════════╗
║                   🧠  XuanShu AGENT  🧠                      ║
║                  玄枢 AI助手 - 启动器                         ║
╚═══════════════════════════════════════════════════════════════╝
""")

    def print_step(self, step: str, description: str = ""):
        """打印步骤信息"""
        print(f"\n{Fore.CYAN}▶ {step}")
        if description:
            print(f"  {description}")

    def print_success(self, msg: str):
        print(f"{Fore.GREEN}✅ {msg}")

    def print_warning(self, msg: str):
        print(f"{Fore.YELLOW}⚠️ {msg}")

    def print_error(self, msg: str):
        print(f"{Fore.RED}❌ {msg}")

    def print_info(self, msg: str):
        print(f"{Fore.BLUE}ℹ️ {msg}")

    def check_python_version(self) -> bool:
        """检查Python版本"""
        self.print_step("检查Python版本", "需要Python 3.8+")
        version = sys.version_info

        if version >= (3, 8):
            self.print_success(f"Python {version.major}.{version.minor}.{version.micro}")
            return True
        else:
            self.print_error(f"Python版本过低: {version.major}.{version.minor}")
            self.print_info("请更新Python到3.8或更高版本")
            return False

    def check_dependencies(self) -> List[str]:
        """检查依赖是否已安装"""
        self.print_step("检查依赖", "验证所需的Python包")

        missing = []
        required_packages = []

        if os.path.exists(self.requirements_file):
            with open(self.requirements_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        pkg = line.split('>=')[0].split('==')[0].strip()
                        if pkg:
                            required_packages.append(pkg)

        for pkg in required_packages:
            try:
                __import__(pkg.replace('-', '_'))
                self.print_success(f"{pkg}")
            except ImportError:
                self.print_warning(f"{pkg} - 未安装")
                missing.append(line)

        return missing

    def install_dependencies(self, dependencies: List[str]) -> bool:
        """安装依赖"""
        self.print_step("安装依赖", "自动安装缺失的包")

        try:
            cmd = [sys.executable, '-m', 'pip', 'install', '-r', self.requirements_file]
            self.print_info(f"执行: {' '.join(cmd)}")

            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True)

            if result.returncode == 0:
                self.print_success("依赖安装完成")
                return True
            else:
                self.print_error("依赖安装失败")
                print(result.stderr)
                return False
        except Exception as e:
            self.print_error(f"安装过程出错: {e}")
            return False

    def check_ollama_installed(self) -> bool:
        """检查Ollama是否已安装"""
        try:
            result = subprocess.run(
                ['ollama', '--version'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                self.print_success(f"Ollama已安装: {version}")
                return True
        except FileNotFoundError:
            pass

        self.print_warning("Ollama未安装")
        self.print_info("请访问 https://ollama.com/download 下载安装")
        return False

    def is_ollama_running(self) -> bool:
        """检查Ollama是否正在运行"""
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=2)
            if response.status_code == 200:
                self.print_success("Ollama正在运行")
                return True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            pass

        return False

    def start_ollama(self) -> bool:
        """尝试启动Ollama"""
        self.print_step("启动Ollama", "尝试启动Ollama服务")

        try:
            if sys.platform == 'win32':
                subprocess.Popen(
                    ['ollama', 'serve'],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                subprocess.Popen(['ollama', 'serve'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            self.print_info("正在启动Ollama...等待5秒")
            time.sleep(5)

            if self.is_ollama_running():
                self.print_success("Ollama启动成功")
                return True
            else:
                self.print_warning("等待超时，请手动检查Ollama状态")
                return False

        except Exception as e:
            self.print_error(f"启动失败: {e}")
            return False

    def get_ollama_models(self) -> List[Dict]:
        """获取Ollama中已有的模型"""
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = data.get('models', [])
                return models
        except Exception as e:
            self.print_error(f"获取模型列表失败: {e}")

        return []

    def select_provider(self) -> str:
        """选择模型提供商"""
        self.print_step("选择模型提供商", "请选择要使用的模型类型")

        print(f"\n{Fore.CYAN}可用提供商:")
        print(f"  1. Ollama (本地模型，推荐)")
        print(f"  2. OpenAI 兼容 API")
        print(f"  3. 自定义 API")

        while True:
            choice = input(f"\n{Fore.GREEN}请选择 [1-3]: ").strip()

            if choice == '1':
                return 'ollama'
            elif choice == '2':
                return 'openai'
            elif choice == '3':
                return 'custom'

            self.print_error("无效的选择，请重试")

    def has_saved_model_config(self) -> bool:
        """检查是否有已保存的模型配置"""
        try:
            from model_providers import config_manager
            current = config_manager.current_config
            if current and current.model_name:
                return True
        except:
            pass
        return False

    def is_saved_model_available(self, model_name: str) -> bool:
        """检查已保存的模型是否在可用列表中"""
        models = self.get_ollama_models()
        return any(m.get('name') == model_name for m in models)

    def setup_ollama(self) -> bool:
        """设置Ollama模型"""
        self.print_step("设置 Ollama", "配置本地模型")

        if not self.check_ollama_installed():
            return False

        is_running = self.is_ollama_running()

        if not is_running:
            print()
            self.print_warning("检测到Ollama未运行")
            print(f"\n{Fore.YELLOW}请按以下步骤操作:")
            print(f"  1. 打开一个新的终端窗口")
            print(f"  2. 输入命令: {Fore.CYAN}ollama serve{Fore.YELLOW}")
            print(f"  3. 等待Ollama启动完成")
            print()
            input(f"{Fore.GREEN}Ollama启动完成后，按回车键继续...")

            is_running = self.is_ollama_running()
            if not is_running:
                self.print_error("Ollama仍未运行，无法继续")
                return False

        models = self.get_ollama_models()

        if not models:
            self.print_warning("没有找到已安装的模型")
            print()
            pull = input(f"{Fore.YELLOW}是否现在下载一个模型? [Y/n]: ").strip().lower()
            if pull in ('', 'y', 'yes'):
                self.pull_ollama_model()
                models = self.get_ollama_models()
                if not models:
                    self.print_error("没有可用的模型")
                    return False
            else:
                self.print_error("没有可用的模型")
                return False

        saved_model_available = False
        if self.has_saved_model_config():
            try:
                from model_providers import config_manager
                saved_model = config_manager.current_config.model_name
                if self.is_saved_model_available(saved_model):
                    self.print_success(f"检测到已保存的模型: {saved_model}")
                    print(f"{Fore.GREEN}将直接使用该模型，无需重新选择")
                    return True
                else:
                    self.print_warning(f"已保存的模型 '{saved_model}' 不可用")
            except:
                pass

        print(f"\n{Fore.CYAN}已安装的模型:")
        for i, model in enumerate(models, 1):
            model_name = model.get('name', 'unknown')
            size = model.get('size', 0)
            size_str = self._format_size(size)
            print(f"  {i}. {model_name} ({size_str})")

        print(f"\n{Fore.YELLOW}请选择要使用的模型 [1-{len(models)}]:")

        while True:
            choice = input(f"{Fore.GREEN}请选择: ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    selected = models[idx]
                    model_name = selected.get('name', 'unknown')
                    self.print_success(f"已选择模型: {model_name}")

                    self._save_ollama_config(model_name)
                    return True

            self.print_error("无效的选择，请重试")

    def _format_size(self, size: int) -> str:
        """格式化模型大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}TB"

    def _save_ollama_config(self, model_name: str):
        """保存Ollama配置"""
        from model_providers import config_manager, ModelConfig, ProviderType

        config = ModelConfig(
            provider=ProviderType.OLLAMA,
            name="ollama-default",
            model_name=model_name,
            api_base="http://localhost:11434",
            api_key=""
        )

        existing = config_manager.get_config("ollama-default")
        if existing:
            config_manager.update_config(config)
        else:
            config_manager.add_config(config)

        config_manager.set_current("ollama-default")
        self.print_success("配置已保存")

    def pull_ollama_model(self):
        """下载Ollama模型"""
        print(f"\n{Fore.CYAN}推荐模型:")
        print(f"  1. qwen2.5-coder:7b (代码能力强，推荐)")
        print(f"  2. qwen2.5:7b (通用对话)")
        print(f"  3. llama3:8b (通用对话)")
        print(f"  4. phi3:3.8b (轻量级)")

        print(f"\n{Fore.YELLOW}请选择要下载的模型 [1-4] 或输入模型名称:")

        choice = input(f"{Fore.GREEN}请选择: ").strip()

        model_map = {
            "1": "qwen2.5-coder:7b",
            "2": "qwen2.5:7b",
            "3": "llama3:8b",
            "4": "phi3:3.8b"
        }

        model_name = model_map.get(choice, choice if choice else "qwen2.5-coder:7b")

        self.pull_model(model_name)

    def pull_model(self, model_name: str) -> bool:
        """下载模型"""
        self.print_step(f"下载模型", f"正在下载 {model_name}")

        try:
            print(f"{Fore.YELLOW}这可能需要几分钟时间，请耐心等待...")
            print(f"{Fore.YELLOW}按 Ctrl+C 可以取消\n")

            process = subprocess.Popen(
                ['ollama', 'pull', model_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            for line in process.stdout:
                print(f"  {line.strip()}")

            process.wait()

            if process.returncode == 0:
                self.print_success(f"模型 {model_name} 下载完成")
                return True
            else:
                self.print_error(f"模型下载失败")
                return False

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}下载已取消")
            process.terminate()
            return False
        except Exception as e:
            self.print_error(f"下载出错: {e}")
            return False

    def setup_external_api(self) -> bool:
        """设置外部API模型"""
        from model_providers import config_manager, ModelConfig, ProviderType

        print(f"\n{Fore.CYAN}配置外部API模型:")

        api_base = input(f"{Fore.GREEN}API地址: ").strip()
        if not api_base:
            self.print_error("API地址不能为空")
            return False

        model_name = input(f"{Fore.GREEN}模型名称: ").strip()
        if not model_name:
            self.print_error("模型名称不能为空")
            return False

        api_key = input(f"{Fore.GREEN}API密钥 (可选): ").strip()

        provider_map = {
            'openai': ProviderType.OPENAI_COMPATIBLE,
            'custom': ProviderType.CUSTOM
        }

        provider = self.selected_provider
        provider_type = provider_map.get(provider, ProviderType.CUSTOM)

        config = ModelConfig(
            provider=provider_type,
            name=f"{provider}-custom",
            model_name=model_name,
            api_base=api_base,
            api_key=api_key
        )

        config_manager.add_config(config)
        config_manager.set_current(f"{provider}-custom")
        self.print_success("配置已保存")

        return True

    def select_interface(self) -> str:
        """选择界面"""
        self.print_step("选择界面", "请选择使用方式")

        print(f"\n{Fore.CYAN}可用界面:")
        print(f"  1. 命令行界面 (CLI)")
        print(f"  2. Web界面")

        while True:
            choice = input(f"\n{Fore.GREEN}请选择 [1-2]: ").strip()

            if choice == '1':
                return 'cli'
            elif choice == '2':
                return 'web'

            self.print_error("无效的选择，请重试")

    def start_web_interface(self, background: bool = False) -> bool:
        """启动 Web 界面。
        Args:
            background: 如果 True，启动后台线程并立即返回；如果 False，阻塞等待健康检查。
        """
        self.print_step("启动 Web 界面", "正在启动 Web 服务...")
        proc = subprocess.Popen([sys.executable, 'web_app.py'], cwd=self.project_root)

        if background:
            # 后台模式：启动后立即返回
            self.print_success(f"✅ Web 界面已在后台启动！请访问：http://{WEB_HOST}:{WEB_PORT}")
            self.print_info("💡 Web 界面和 CLI 将同时运行，数据互通。")
            return True

        # 阻塞模式：等待健康检查（原有逻辑）
        self.print_info("等待 Web 服务启动...")

        max_wait = 30
        waited = 0
        health_ok = False
        health_host = "127.0.0.1"

        while waited < max_wait:
            try:
                # 先检查根路径
                resp = requests.get(f"http://{health_host}:{WEB_PORT}/", timeout=2)
                if resp.status_code == 200:
                    # 根路径正常，再检查 API 端点
                    resp2 = requests.get(f"http://{health_host}:{WEB_PORT}/api/skills", timeout=2)
                    if resp2.status_code == 200:
                        data = resp2.json()
                        if data.get('success'):
                            self.print_success(f"✅ Web 界面启动成功！请访问：http://{WEB_HOST}:{WEB_PORT}")
                            health_ok = True
                            break
                        else:
                            error_msg = data.get("error", "未知错误")
                            self.print_warning(f"⚠️ /api/skills 返回失败：{error_msg}")
                    else:
                        self.print_warning(f"⚠️ /api/skills 状态码：{resp2.status_code}")
                else:
                    self.print_warning(f"⚠️ 根路径状态码：{resp.status_code}")
            except requests.exceptions.ConnectionError:
                pass
            except Exception as e:
                self.print_warning(f"⚠️ 健康检查异常：{e}")
                time.sleep(1)
                waited += 1

        if not health_ok:
            self.print_error(f"❌ Web 界面启动超时 ({max_wait}秒)，请检查日志或确保端口 {WEB_PORT} 未被占用。")
            try:
                stdout, stderr = proc.communicate(timeout=2)
                if stdout:
                    self.print_info(f"[子进程标准输出]\n{stdout.decode()}")
                if stderr:
                    self.print_info(f"[子进程标准错误]\n{stderr.decode()}")
            except:
                pass
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except:
                proc.kill()
            input(Fore.YELLOW + "按回车键返回..." + Style.RESET_ALL)
            if proc.poll() is None:
                proc.kill()
            return False

        return True

    def select_cli_mode(self) -> str:
        """CLI 模式下的子选择：单机模式或协作模式"""
        self.print_step("选择运行模式", "请选择 Agent 的运行模式")
        print(f"\n{Fore.CYAN}可用模式:")
        print(f"  1. 单机模式")
        print(f"  2. 协作模式")
        
        while True:
            choice = input(f"\n{Fore.GREEN}请选择 [1-2]: ").strip()
            if choice == '1':
                return 'standalone'
            elif choice == '2':
                # 协作子菜单
                print(f"\n{Fore.CYAN}协作操作:")
                print(f"  1. 创建房间")
                print(f"  2. 加入房间")
                sub = input(f"{Fore.GREEN}请选择 [1-2]: ").strip()
                if sub == '1':
                    # 创建房间需要使用 Web 界面
                    confirm = input(f"{Fore.YELLOW}创建房间需要使用 Web 界面，是否现在启动 Web？ [Y/n]: ").strip().lower()
                    if confirm in ('', 'y', 'yes'):
                        return 'web'  # 切换到 Web 模式
                    else:
                        self.print_info("已取消，返回主菜单。")
                        return 'standalone'  # 视为单机模式
                elif sub == '2':
                    # 加入房间 - 当前版本限制
                    self.print_warning("加入房间功能正在开发中，当前请在 Web 界面使用集群协作。")
                    self.print_info("已切换回单机模式。")
                    return 'standalone'
                else:
                    self.print_error("无效选择，请重试")
            else:
                self.print_error("无效选择，请重试")

    def run(self):
        """运行启动器"""
        self.print_banner()
        
        # ==================== 跨平台兼容性处理 ====================
        # Windows 环境自动检测 Docker 可用性，不可用则降级到 subprocess
        if sys.platform == 'win32':
            try:
                subprocess.run(['docker', '--version'], capture_output=True, check=True, timeout=2)
            except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                os.environ['SANDBOX_ENABLED'] = 'false'
                print("⚠️ 检测到Windows环境但Docker不可用，已自动禁用Docker沙箱模式，降级到subprocess执行。", file=sys.stderr)
        
        try:
            ok = self.check_python_version()
            if not ok:
                input(f"\n{Fore.RED}按回车键退出...")
                return

            missing = self.check_dependencies()
            if missing:
                print()
                install = input(f"{Fore.YELLOW}是否自动安装缺失的依赖? [Y/n]: ").strip().lower()
                if install in ('', 'y', 'yes'):
                    ok = self.install_dependencies(missing)
                    if not ok:
                        self.print_warning("继续尝试启动...")

            print()
            self.selected_provider = self.select_provider()

            if self.selected_provider == 'ollama':
                ok = self.setup_ollama()
                if not ok:
                    print()
                    retry = input(f"{Fore.YELLOW}是否选择其他提供商? [Y/n]: ").strip().lower()
                    if retry not in ('', 'y', 'yes'):
                        return
                    self.selected_provider = None
                    while not self.selected_provider:
                        self.selected_provider = self.select_provider()
                    if self.selected_provider != 'ollama':
                        self.setup_external_api()
            else:
                self.setup_external_api()

            if not self.selected_provider:
                self.print_error("未选择提供商")
                return

            print()
            interface = self.select_interface()

            print(f"\n{Fore.GREEN}═══════════════════════════════════════════════════════════════")
            print(f"{Fore.GREEN}                        🚀 启动 Agent")
            print(f"{Fore.GREEN}═══════════════════════════════════════════════════════════════")
            from model_providers import config_manager
            current = config_manager.current_config
            print(f"{Fore.BLUE}模型: {current.name} ({current.model_name})")
            print(f"{Fore.BLUE}界面: {'Web' if interface == 'web' else 'CLI'}")
            print()

            time.sleep(1)

            if interface == 'web':
                self.start_web_interface()
                return

            else:
                # CLI 模式下选择更细粒度的运行模式
                cli_mode = self.select_cli_mode()
                if cli_mode == 'web':
                    self.start_web_interface(background=True)
                else:
                    # 单机模式运行
                    from agent import UniversalAgent
                    agent = UniversalAgent()
                    agent.run()

        except KeyboardInterrupt:
            print(f"\n\n{Fore.YELLOW}👋 已取消")
        except Exception as e:
            print(f"\n{Fore.RED}发生错误：{e}")
            import traceback
            traceback.print_exc()


def main():
    launcher = Launcher()
    launcher.run()


if __name__ == "__main__":
    main()