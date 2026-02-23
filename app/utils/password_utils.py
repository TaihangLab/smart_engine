#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
密码处理工具模块
提供密码哈希和验证功能
直接使用 bcrypt 库（2025年推荐方式）
"""

import bcrypt
import re
import logging

logger = logging.getLogger(__name__)


# 默认工作因子（推荐值：开发环境 10-12，生产环境 12-14）
DEFAULT_ROUNDS = 12


def hash_password(password: str, rounds: int = DEFAULT_ROUNDS) -> str:
    """
    对密码进行哈希处理

    Args:
        password: 明文密码
        rounds: 工作因子，越高越安全但越慢（默认 12）

    Returns:
        哈希后的密码（60字符字符串）

    Raises:
        ValueError: 密码为空时
    """
    if not password:
        raise ValueError("密码不能为空")

    # 转换为字节
    password_bytes = password.encode('utf-8')

    # 生成盐并哈希
    salt = bcrypt.gensalt(rounds=rounds)
    hashed = bcrypt.hashpw(password_bytes, salt)

    # 返回字符串形式用于存储
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码与哈希密码是否匹配

    Args:
        plain_password: 明文密码
        hashed_password: 哈希密码

    Returns:
        密码是否匹配
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"密码验证失败: {e}")
        return False


def needs_rehash(hashed_password: str, min_rounds: int = DEFAULT_ROUNDS) -> bool:
    """
    检查哈希是否使用较少的工作因子，需要重新哈希

    Args:
        hashed_password: 存储的哈希密码
        min_rounds: 最小工作因子要求

    Returns:
        是否需要重新哈希
    """
    try:
        # 从哈希中提取工作因子（格式：$2b$12$...）
        parts = hashed_password.split('$')
        if len(parts) >= 3:
            current_rounds = int(parts[2])
            return current_rounds < min_rounds
        return True
    except (ValueError, IndexError):
        return True


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    验证密码强度

    Args:
        password: 待验证的密码

    Returns:
        (是否符合要求, 错误信息)
    """
    if len(password) < 8:
        return False, "密码长度至少为8位"

    if len(password) > 128:
        return False, "密码长度不能超过128位"

    if not re.search(r"[A-Z]", password):
        return False, "密码必须包含至少一个大写字母"

    if not re.search(r"[a-z]", password):
        return False, "密码必须包含至少一个小写字母"

    if not re.search(r"\d", password):
        return False, "密码必须包含至少一个数字"

    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        return False, "密码必须包含至少一个特殊字符"

    return True, "密码强度符合要求"


# 示例用法
if __name__ == "__main__":
    # 测试密码哈希和验证
    password = "TestPassword123!"
    hashed = hash_password(password)
    print(f"明文密码: {password}")
    print(f"哈希密码: {hashed}")
    print(f"哈希长度: {len(hashed)} 字符")

    # 验证正确密码
    result = verify_password(password, hashed)
    print(f"验证正确密码: {result}")

    # 验证错误密码
    result = verify_password("wrong_password", hashed)
    print(f"验证错误密码: {result}")

    # 检查是否需要重新哈希
    print(f"是否需要重新哈希 (rounds < 12): {needs_rehash(hashed)}")
    print(f"是否需要重新哈希 (rounds < 15): {needs_rehash(hashed, min_rounds=15)}")

    # 测试密码强度验证
    print(f"强密码验证: {validate_password_strength(password)}")
    print(f"弱密码验证: {validate_password_strength('weak')}")
