from astrbot.api.event import filter, AstrMessageEvent
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
        self.Tinyapi_base_url = "https://api.tinyaii.top"
        self.Nteguide_base_url = "https://nteguide.com/"
        self.net_search_api = "/v1/nte/search"
        self.headers = {"Authorization": self.config.get("tinyapi_key", "")}
        self.logger.info(f"tinyapi_key: {self.config.get("tinyapi_key", "")}")

    async def create_session(self):
        session = aiohttp.ClientSession(
            headers=self.headers
        )
        return session

    @filter.command_group("异环")
    def 异环(self):
        pass
    
    @异环.command("攻略")
    async def get_guide_url(self, event: AstrMessageEvent, keyword: str):
        session = await self.create_session()
        async with session.get(self.Tinyapi_base_url + self.net_search_api + f"?keyword={keyword}&type=guide") as resp:
            full_data = await resp.json()
            next_url = full_data.get("data", {}).get("items", [])[0].get("url", "")
            the_full_url = self.Nteguide_base_url + next_url
            yield event.plain_result(the_full_url)
