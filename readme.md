# Agent

### agent.py

包装llm为agent

# Config

目前没用上

# ErrorClass

### errorclass.py

自定义的异常类型

# examples

使用agent创建文件所允许的工作目录，

目前所有的文件创建都只能在这个目录中执行

# LLM

### llm.py

实例化一个llm_client，

方法：

	think：向llm传入相关信息，返回执行结果

# LLMTools

### outside_tools.py

可以调用的外部工具

### sys_tools.py

可以调用的系统工具

# MCP_server

### mcp_manager.py

mcp管理工具，包含功能：

	开启一个session；

	返回mcp中可toolslist

	将mcp返回的toolslist转换为llm可读的格式

	将llm返回的toolcall转换为mcp可调用的格式，并返回调用结果

### mcp_server.py

	将工具注册进mcp

# path_manager

### pathmanager.py

路径管理工具

# Prompt

### prompt.py

提示词信息

# .env

程序所需要的环境变量

谷歌搜索api网址：[serpapi.com/users/sign_in](https://serpapi.com/users/sign_in)

# main.py

程序运行的主函数
