# API响应格式修复计划

## 目标
修复项目中API响应的命名格式问题，确保所有API响应都使用蛇形命名（snake_case）而非驼峰命名（camelCase）。

## 具体任务
1. 检查所有Pydantic响应模型，移除或修改alias_generator=to_camel配置
2. 检查所有API端点的响应数据格式
3. 统一整个项目的响应格式为蛇形命名
4. 确保前后端数据格式一致性

## 实施步骤
1. 首先搜索项目中的Pydantic模型定义
2. 查找包含alias_generator=to_camel的配置
3. 检查API端点返回的数据结构
4. 修改相关模型和端点以使用蛇形命名
5. 测试修改后的功能