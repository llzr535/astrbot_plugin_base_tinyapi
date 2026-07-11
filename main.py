import asyncio
from dataclasses import dataclass
import os
import tempfile
import time
from typing import Dict, List, Optional, TypedDict
from playwright.async_api import async_playwright

import aiohttp

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

class search_result(TypedDict):
    name: str
    type: str
    url: str

@dataclass
class SessionEntry:
    results: List[search_result]
    last_access: float

class nte_search_plugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.Tinyapi_base_url = "https://api.tinyaii.top"
        self.Nteguide_base_url = "https://nteguide.com/"
        self.net_search_api = "/v1/nte/search"
        self.headers = {"Authorization": config.get("tinyapi_key", "")}
        self.session_timeout = config.get("timeout", int) or 60
        self._session_data: Dict[str, SessionEntry] = {}
        self._session_lock: Dict[str, asyncio.Lock] = {}
        self.playwright = None
        self._browser = None
        self._cleanup_task: Optional[asyncio.Task] = None

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._session_lock:
            self._session_lock[session_id] = asyncio.Lock()
        return self._session_lock[session_id]

    async def _cleanup_expired_sessions(self) -> None:
        current_time = time.time()
        session_timeout = self.session_timeout
        expired_session = [
            sid for sid, entry in self._session_data.items()
            if current_time - entry.last_access > session_timeout
        ]
        for sid in expired_session:
            async with await self._get_session_lock(sid):
                if sid in self._session_data:
                    del self._session_data[sid]
                if sid in self._session_lock:
                    del self._session_lock[sid]
            logger.debug(f"已清理过期会话: {sid}")
        if expired_session:
            logger.info(f"已清理 {len(expired_session)} 个过期会话")

    async def _start_clean_task(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(10)
            try:
                await self._cleanup_expired_sessions()
            except Exception as e:
                logger.warning(f"清理过期会话时出错: {e}")

    def _update_session_access(self, session_id: str) -> None:
        if session_id in self._session_data:
            self._session_data[session_id].last_access = time.time()

    async def _init_browser(self) -> bool:
        if self._browser is not None:
            return True
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            logger.info("Playwright 浏览器已初始化")
            return True
        except Exception as e:
            logger.error(f"初始化 Playwright 浏览器时发生未知错误: {e}")
            return False

    async def search_nte_result(self, keyword: str) -> List[search_result]:
        results = []
        api_url = self.Tinyapi_base_url + self.net_search_api + f"?keyword={keyword}"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                resp = await session.get(url=api_url)
                resp.raise_for_status()
                full_data = await resp.json()
                all_need_data = full_data.get("data", {}).get("items", [])
                for item in all_need_data:
                    results.append({
                        "name": item.get("name", ""),
                        "type": item.get("type", ""),
                        "url": self.Nteguide_base_url + item.get("url", "")
                    })
                return results
        except Exception as e:
            logger.error(f"搜索攻略时出错: {e}")
            return []

    async def _capture_page(self, url: str) -> Optional[str]:
        browser_ok = await self._init_browser()
        if not browser_ok:
            return None
        page = None
        try:
            page = await self._browser.new_page()
            await page.goto(url, wait_until="load", timeout=60000)
            await page.wait_for_timeout(1500)
            temp_dir = tempfile.gettempdir()
            url_hash = abs(hash(url))
            screenshot_path = os.path.join(temp_dir, f"wiki_screenshot_{url_hash}.png")
            await page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"截图已保存: {screenshot_path}")
            return screenshot_path
        except Exception as e:
            logger.error(f"截图时出错: {e}")
            return None
        finally:
            if page:
                await page.close()

    @filter.command("异环攻略")
    async def nte_search(self, event: AstrMessageEvent, keyword: str):
        await self._start_clean_task()
        if not keyword:
            yield event.plain_result("请输入搜索关键词")
            return
        logger.info(f"搜索关键词: {keyword}")
        try:
            results = await self.search_nte_result(keyword)
        except Exception as e:
            logger.error(f"搜索攻略时出错: {e}")
            yield event.plain_result("搜索攻略时出错")
            return
        session_id = event.session_id
        lock = await self._get_session_lock(session_id)
        async with lock:
            self._session_data[session_id] = SessionEntry(
                results=results,
                last_access=time.time()
            )
        msg_lines = [f"找到 {len(results)} 个与 '{keyword}' 相关的结果:"]
        for r in results:
            msg_lines.append(f"{r['type']}. {r['name']}")
        msg_lines.append(f"\n请回复数字选择要查看的页面（{self.session_timeout}秒内有效）")
        yield event.plain_result("\n".join(msg_lines))

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_selection(self, event: AstrMessageEvent):
        session_id = event.session_id
        lock = await self._get_session_lock(session_id)
        async with lock:
            if session_id not in self._session_data:
                return
            self._update_session_access(session_id)
            message = event.message_str.strip()
            try:
                selection = int(message)
            except ValueError:
                return
            entry = self._session_data[session_id]
            results = entry.results
            if selection < 1 or selection > len(results):
                yield event.plain_result(f"无效选择，请输入 1-{len(results)} 之间的数字")
                return
            selected = results[selection - 1]
            url = selected["url"]
            name = selected["name"]
        yield event.plain_result(f"正在获取 '{name}' 的页面，请稍候...")
        try:
            screenshot_path = await self._capture_page(url)
            if screenshot_path and os.path.exists(screenshot_path):
                yield event.image_result(screenshot_path)
                try:
                    os.remove(screenshot_path)
                except OSError:
                    logger.warning(f"无法删除临时截图文件: {screenshot_path}")
            else:
                error_text = f"页面: {name}\n链接: {url}"
                try:
                    yield event.image_result(await event.text_to_image(error_text))
                except Exception as e:
                    logger.error(f"生成错误图片失败: {e}")
                    yield event.plain_result(error_text)
        except Exception as e:
            logger.error(f"截图过程出错: {e}")
            error_text = f"页面: {name}\n链接: {url}"
            try:
                yield event.image_result(await event.text_to_image(error_text))
            except Exception:
                yield event.plain_result(error_text)

    async def terminate(self):
        logger.info("正在关闭 异环攻略插件 浏览器实例...")
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._browser:
            try:
                await self._browser.close()
                logger.info("浏览器实例已关闭")
            except Exception as e:
                logger.warning(f"关闭浏览器实例时出错: {e}")
            finally:
                self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
                logger.info("Playwright 已停止")
            except Exception as e:
                logger.warning(f"停止 Playwright 时出错: {e}")
            finally:
                self._playwright = None
        self._session_data.clear()
        self._session_lock.clear()
        logger.info("异环攻略插件 已卸载")