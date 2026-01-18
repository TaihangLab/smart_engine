#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
密码处理工具模块
提供密码哈希和验证功能
"""

from passlib.context import CryptContext
import re


# 创建密码上下文，优先使用bcrypt，如果不可用则使用argon2或pbkdf2
try:
    # 尝试使用bcrypt
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    # 测试bcrypt是否可用
    pwd_context.hash("test")
except Exception:
    try:
        # 如果bcrypt不可用，尝试使用argon2
        pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
        pwd_context.hash("test")
    except Exception:
        # 如果argon2也不可用，使用pbkdf2_sha256（纯Python实现）
        pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    对密码进行哈希处理
    
    Args:
        password: 明文密码
        
    Returns:
        哈希后的密码
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码与哈希密码是否匹配
    
    Args:
        plain_password: 明文密码
        hashed_password: 哈希密码
        
    Returns:
        密码是否匹配
    """
    return pwd_context.verify(plain_password, hashed_password)


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
    print(f"验证结果: {verify_password(password, hashed)}")
    print(f"验证错误密码: {verify_password('wrong_password', hashed)}")
    
    # 测试密码强度验证
    print(validate_password_strength(password))
    print(validate_password_strength("weak"))