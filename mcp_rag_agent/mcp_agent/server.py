import os
from typing import Any
from mcp.server.fastmcp import FastMCP
import httpx
#创建一个对象
mcp = FastMCP("weather_and_search")


async def get_weather(city: str) -> dict[str, Any]:
    """
    :param city:
    :return:
    """
    """
        1.确定查询天气的服务
        2.配置相关的参数，构建请求体
        3.请求服务
       api.weatherapi.com
    """
    #查询当前时间的天气情况
    url = "http://api.weatherapi.com/v1/current.json"
    api_key=""
    parameter = {
        "q": city,
        "key": api_key
    }

    #异步方式来请求
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=parameter)
            return response.json()
        except Exception as err:
            return {"error": f"请求失败: {str(err)}"}

async def format_data(json_data):
    """
    将天气数据转成已读文本
    :param json_data:
    :return:
    """
    """
    {'location': {'name': 'Shenzhen', 'region': 'Guangdong', 'country': 'China', 'lat': 22.5333, 'lon': 114.1333, 'tz_id': 'Asia/Hong_Kong', 'localtime_epoch': 1745491061, 'localtime': '2025-04-24 18:37'}, 'current': {'last_updated_epoch': 1745490600, 'last_updated': '2025-04-24 18:30', 'temp_c': 27.1, 'temp_f': 80.8, 'is_day': 1, 'condition': {'text': 'Moderate or heavy rain with thunder', 'icon': '//cdn.weatherapi.com/weather/64x64/day/389.png', 'code': 1276}, 'wind_mph': 9.8, 'wind_kph': 15.8, 'wind_degree': 186, 'wind_dir': 'S', 'pressure_mb': 1007.0, 'pressure_in': 29.74, 'precip_mm': 0.0, 'precip_in': 0.0, 'humidity': 89, 'cloud': 75, 'feelslike_c': 29.5, 'feelslike_f': 85.2, 'windchill_c': 27.3, 'windchill_f': 81.2, 'heatindex_c': 29.9, 'heatindex_f': 85.8, 'dewpoint_c': 21.7, 'dewpoint_f': 71.1, 'vis_km': 10.0, 'vis_miles': 6.0, 'uv': 0.2, 'gust_mph': 12.1, 'gust_kph': 19.5}}

    """
    city = json_data.get("location", {}).get("name", "未知")
    country = json_data.get("location", {}).get("country", "未知")
    temp = json_data.get("current", {}).get("temp_c", "N/A")
    humidity = json_data.get("current", {}).get("humidity", "N/A")
    wind_speed = json_data.get("current", {}).get("wind_kph", "N/A")
    condition = json_data.get("current", {}).get("condition", {}).get("text", "未知")
    return f"当前城市{country}.{city}\n 温度:{temp}，湿度:{humidity}，风速:{wind_speed}， 天气情况:{condition}"

#定义成一个工具
@mcp.tool()
async def query_weather(city: str) -> str:
    """
    输入指定的城市名(英文)，返回今日天气情况
    :param city: 城市名称(需使用英文)
    :return: 格式化之后的天气信息
    """
    data = await get_weather(city)
    weather_info = await format_data(json_data=data)
    print("weather_info:", weather_info)
    return weather_info


@mcp.tool()
async def search_web(query: str, count: int = 5) -> str:
    """
    Search the web using You.com Search API.
    Supports 100 free searches/day without API key; set YDC_API_KEY for higher limits.
    """
    if not query or not query.strip():
        return "error: query is required"

    if count < 1:
        count = 1
    if count > 10:
        count = 10

    url = "https://api.you.com/v1/agents/search"
    params = {"query": query.strip(), "count": count}
    headers = {}
    api_key = os.getenv("YDC_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params, headers=headers)

        if response.status_code == 401:
            return "error: unauthorized. set YDC_API_KEY or use free-tier quota"
        if response.status_code == 429:
            return "error: rate limited by You.com API, please retry later"
        if response.status_code >= 400:
            return f"error: search request failed ({response.status_code}): {response.text[:300]}"

        data = response.json()
        web_results = data.get("results", {}).get("web", []) or []
        news_results = data.get("results", {}).get("news", []) or []

        if not web_results and not news_results:
            return "No results found."

        lines = [f"Search results for: {query}"]
        for idx, item in enumerate((web_results + news_results)[:count], start=1):
            title = item.get("title", "Untitled")
            link = item.get("url", "")
            desc = item.get("description", "")
            lines.append(f"{idx}. {title}\n   {link}\n   {desc}")

        return "\n".join(lines)
    except Exception as err:
        return f"error: search request exception: {str(err)}"

if __name__ == "__main__":
    # asyncio.run(query_weather("shenzhen"))
    mcp.run(transport="stdio")

    # server和client都在同一个服务器上，std IO流进行交互，提高交互效率
    # 如果server端部署在远程，那需要使用sse的方式
