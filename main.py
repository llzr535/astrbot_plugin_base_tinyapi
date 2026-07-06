from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

import asyncio
import aiohttp

@register(
    "astrbot_plugin_base_tinyapi",
    "llzr535",
    "基于tinyapi制作的异环攻略搜索插件，返回一个基于异环wiki的攻略链接",
    "1.0.0",
    "https://github.com/NightDust981989/astrbot_plugin_base_tinyapi"
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.logger = logger

        Tinyapi_base_url = "https://api.tinyaii.top"
        Nteguide_base_url = "https://nteguide.com/"
        net_search_api = "/v1/nte/search"
        headers = {"Authorization": self.config.get("tinyapi_key", "")}
        self.logger.info(f"tinyapi_key: {self.config.get("tinyapi_key", "")}")

    async def create_session(self):
        session = aiohttp.ClientSession(
            headers=headers
        )
        return session

    @filter.command("异环攻略")
    async def get_guide_url(self, event: AstrMessageEvent, keyword: str, type = "guide"):
        session = await self.create_session()
        async with session.get(Tinyapi_base_url + net_search_api + f"?keyword={keyword}&type={type}") as resp:
            full_data = await resp.json()
            next_url = full_data.get("data", {}).get("items", [])[0].get("url")
            the_full_url = Nteguide_base_url + next_url
            yield MessageEventResult(the_full_url)