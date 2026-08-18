# ErrorClass

### errorclass.py

自定义的异常类型



# LLM

### llm.py

实例化一个llm_client，

方法：

​	think：向llm传入相关信息，返回执行结果



# MCP_server

### mcp_manager.py

mcp管理工具，包含功能：

​	开启一个session；

​	返回mcp中可toolslist

​	将mcp返回的toolslist转换为llm可读的格式

​	将llm返回的toolcall转换为mcp可调用的格式，并返回调用结果

### mcp_server.py

​	mcp中的工具，目前包含：

​		当前时间查询：get_current_time

​		在线搜索工具：search_information

​		天气查询工具：weather_query



# path_manager

### pathmanager.py

路径管理工具



# Prompt

### prompt.py

提示词信息



# .env

程序所需要的环境变量



# main.py

程序运行的主函数