# Smart Engine 贡献指南

本文档定义了 Smart Engine 项目的开发规范和贡献规则。

## 📋 开发规范

### 脚本使用规范

#### 🔴 禁止使用 Shell 脚本
本项目**严格禁止**使用 Shell 脚本 (.sh) 文件，包括但不限于：
- 配置脚本
- 部署脚本
- 自动化脚本
- 工具脚本

#### ✅ 只使用 Python 脚本
所有自动化脚本必须使用 Python 编写：
- 使用 `.py` 文件扩展名
- 遵循项目的 Python 编码规范
- 支持环境变量自动加载
- 提供详细的错误处理和日志记录

#### 📝 脚本命名规范
- 配置脚本: `setup_*.py`
- 检查脚本: `check_*.py`
- 工具脚本: `tool_*.py`
- 测试脚本: `test_*.py`

### 环境变量管理

#### 环境变量文件
- 使用 `.env.{ENV}` 格式的环境变量文件
- 默认环境为 `dev`: `.env.dev`
- 生产环境使用: `.env.prod`

#### 环境变量加载顺序
```python
# 正确的加载顺序
load_dotenv()  # 加载 .env
ENV = os.getenv("ENV", "dev")
load_dotenv(f".env.{ENV}")  # 加载 .env.dev/.env.prod
```

#### 必需的环境变量检查
所有脚本必须检查必需的环境变量：
```python
required_vars = ['RABBITMQ_HOST', 'RABBITMQ_USER', 'RABBITMQ_PASSWORD']
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    print(f"❌ 缺少环境变量: {', '.join(missing_vars)}")
    sys.exit(1)
```

## 🛠️ 开发工具

### 推荐工具链
- **Python**: 3.11.9+
- **虚拟环境**: conda (推荐) 或 venv
- **依赖管理**: pip + requirements.txt
- **代码格式化**: black
- **代码检查**: flake8
- **类型检查**: mypy

### 环境配置
```bash
# 创建虚拟环境
conda create -n smart_engine python=3.11.9
conda activate smart_engine

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖
pip install black flake8 mypy
```

## 📁 项目结构

### 目录规范
```
smart_engine-nacos/
├── app/                    # 应用程序代码
├── docs/                   # 文档（被Git管理）
│   ├── setup/             # 配置脚本
│   ├── *.md               # 各种文档
│   └── CONTRIBUTING.md    # 本文档
├── .wiki/                  # 知识库（不被Git管理）
├── tests/                  # 测试代码
├── requirements.txt        # Python依赖
└── README.md              # 项目说明
```

### 文件组织原则
- **docs/**: 存放部署、配置、使用文档
- **.wiki/**: 存放技术知识库和详细API文档
- **scripts/**: 不使用，统一放在 docs/setup/
- **tools/**: 不使用，统一使用 Python 脚本

## 🔧 配置脚本开发

### 脚本模板
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本功能描述
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
ENV = os.getenv("ENV", "dev")
load_dotenv(f".env.{ENV}")

def main():
    """主函数"""
    # 检查环境变量
    required_vars = ['VAR1', 'VAR2']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"❌ 缺少环境变量: {', '.join(missing_vars)}")
        sys.exit(1)

    # 脚本逻辑
    print("✅ 脚本执行成功")

if __name__ == "__main__":
    main()
```

### 错误处理规范
- 使用 try-except 块处理异常
- 提供清晰的错误信息
- 使用适当的退出代码
- 记录详细的错误日志

### 日志规范
```python
import logging
logger = logging.getLogger(__name__)

# 使用 logger 而不是 print
logger.info("信息消息")
logger.warning("警告消息")
logger.error("错误消息")
```

## 📝 代码规范

### Python 编码规范
- 遵循 PEP 8 标准
- 使用类型注解
- 添加详细的文档字符串
- 使用描述性的变量名

### 文档规范
- 所有公共函数和类必须有文档字符串
- 使用 Google 风格的文档字符串
- API 接口要有详细说明
- 更新相关文档

### 提交规范
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type 类型**:
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式化
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建工具或辅助工具的变动

## 🧪 测试规范

### 测试文件结构
```
tests/
├── __init__.py
├── conftest.py              # pytest 配置
├── test_*.py               # 单元测试
├── integration/            # 集成测试
└── fixtures/               # 测试fixtures
```

### 测试覆盖率要求
- 核心业务逻辑: >90%
- API 接口: >80%
- 工具函数: >70%

### 测试运行
```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_api.py

# 生成覆盖率报告
pytest --cov=app --cov-report=html
```

## 🔒 安全规范

### 敏感信息处理
- 密码等敏感信息不应该硬编码
- 使用环境变量存储敏感配置
- 不要在日志中输出敏感信息

### 权限控制
- API 接口要有适当的权限验证
- 数据库操作要有权限检查
- 文件系统操作要有安全检查

## 📚 学习资源

### 推荐阅读
- [PEP 8 - Python 代码风格指南](https://pep8.org/)
- [Google Python 风格指南](https://google.github.io/styleguide/pyguide.html)
- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 官方文档](https://sqlalchemy.org/)

### 相关工具
- [Black 代码格式化](https://black.readthedocs.io/)
- [Flake8 代码检查](https://flake8.pycqa.org/)
- [MyPy 类型检查](https://mypy.readthedocs.io/)
- [Pytest 测试框架](https://pytest.org/)

## 🤝 贡献流程

1. **Fork 项目**
2. **创建特性分支**: `git checkout -b feature/your-feature`
3. **编写代码**: 遵循上述规范
4. **编写测试**: 确保测试覆盖
5. **提交代码**: `git commit -m "feat: add new feature"`
6. **推送分支**: `git push origin feature/your-feature`
7. **创建 Pull Request**

## 📞 联系方式

如有问题，请通过以下方式联系：
- 提交 GitHub Issue
- 发送邮件至开发团队
- 在项目群中讨论

---

*最后更新时间: 2025年1月8日*