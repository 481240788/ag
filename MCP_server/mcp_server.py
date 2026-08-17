from mcp.server.fastmcp import FastMCP
from datetime import datetime
from serpapi import SerpApiClient
from dotenv import load_dotenv
from ErrorClass import SearchError,ApiError
import os,requests


load_dotenv()
mcp = FastMCP("Doraemon")

@mcp.tool()
def get_current_time() -> str:
    """
    获取当前的时间（例如：2026-08-14 14:49:52.692439）
    return:
        当前的时间
    """
    today_date = datetime.today()
    return str(today_date)



@mcp.tool()
def search_information(query:str) -> str:
    """
    在线搜索工具
    """
    search_api = os.getenv('search_api')
    if search_api is None:
        raise ApiError(f'未配置api')
    
    params = {
        'engine':'google',
        'q':query,
        'api_key':search_api,
        'gl':'cn',      #国家代码
        'hl':'zh-cn'    #语言代码
    }

    try:
        client = SerpApiClient(params_dict=params)
        response = client.get_dict()

     # 智能解析:优先寻找最直接的答案
        if "answer_box_list" in response:
            return '\n'.join(response["answer_box_list"])
        if "answer_box" in response and "answer" in response["answer_box"]:
            return '\n'.join(response["answer_box"]['answer'])
        if "knowledge_graph" in response and "description" in response["knowledge_graph"]:
            return response["knowledge_graph"]["description"]

        if "organic_results" in response and response["organic_results"]:
             # 如果没有直接答案，则返回前三个有机结果的摘要
            snippets = [
                f"[{i+1}] {res.get('title', '')}\n{res.get('snippet', '')}"
                for i, res in enumerate(response["organic_results"][:3])
            ]
            return "\n\n".join(snippets)
        return f"对不起，没有找到关于 '{query}' 的信息。"
    
    except Exception as e:
        raise SearchError(f"搜索时发生错误：{e}") from e


@mcp.tool()
def weather_query(city:str) -> str:
    """
    天气查询工具
    input: city(城市名)
    output: str(城市、天气、温度)
    """
    #组装请求头
    url = f'https://wttr.in/{city}?format=j1'

    try:
        #发送get请求
        response = requests.get(url)   
        #判断请求返回状态码是否正常，正常不管，不正常raise出HTTPError
        response.raise_for_status() 
        #将返回的消息requests.text转为json格式
        data = response.json()
        

        #下面这些依赖url返回的数据格式了
        current_condition = data['current_condition'][0]
        weather_desc = current_condition['weatherDesc'][0]["value"]
        temp_c = current_condition['temp_C']

        return f'{city}当前天气:{weather_desc},气温:{temp_c}℃'
    
    except requests.exceptions.RequestException as e:
        raise SearchError(f"查询遇到网络问题:{e}") from e
    
    except (KeyError,IndexError) as e:
        raise SearchError(f"解析天气数据错误，可能是城市名无效:{e}") from e
    
if __name__ == "__main__":
    mcp.run()