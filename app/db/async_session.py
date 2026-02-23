"""
异步数据库会话管理

为 FastAPI 应用提供 AsyncSession 支持，用于高并发场景。
与同步 session.py 共存，逐步迁移到完全异步化。
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# 异步引擎配置
# 将 mysql+pymysql:// 替换为 mysql+aiomysql://
_async_uri = settings.SQLALCHEMY_DATABASE_URI.replace("mysql+pymysql://", "mysql+aiomysql://")

async_engine = create_async_engine(
    _async_uri,
    pool_size=settings.DB_POOL_SIZE,  # 连接池大小：50
    max_overflow=settings.DB_MAX_OVERFLOW,  # 最大溢出连接：100
    pool_timeout=settings.DB_POOL_TIMEOUT,  # 获取连接超时：30秒
    pool_recycle=settings.DB_POOL_RECYCLE,  # 连接回收时间：1小时
    pool_pre_ping=settings.DB_POOL_PRE_PING,  # 连接前预检查
    echo=settings.DB_ECHO,  # SQL调试输出
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    autocommit=settings.DB_AUTOCOMMIT,
    autoflush=settings.DB_AUTOFLUSH,
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False  # 提交后不过期对象，避免懒加载问题
)

async def get_async_db():
    """
    异步数据库会话依赖（用于 API 路由）

    使用示例：
    ```python
    from fastapi import Depends
    from app.db.async_session import get_async_db, AsyncSessionLocal

    @router.get("/users/{id}")
    async def get_user(
        id: int,
        db: AsyncSession = Depends(get_async_db)
    ):
        result = await db.execute(
            select(User).where(User.id == id)
        )
        user = result.scalars().first()
        return user
    ```

    也可以直接使用 AsyncSessionLocal：
    ```python
    async with AsyncSessionLocal() as db:
        result = await db.execute(...)
        await db.commit()
    ```
    """
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()

async def get_async_db_session():
    """
    获取异步数据库会话（用于服务层）

    与 get_async_db 的区别是返回会话对象而非生成器，
    适合在后台任务或服务层直接使用。

    使用示例：
    ```python
    async def my_service_function():
        db = await get_async_db_session()
        try:
            result = await db.execute(...)
            await db.commit()
        finally:
            await db.close()
    ```
    """
    return AsyncSessionLocal()
