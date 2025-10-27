"""
认证工具类
"""
import jwt
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from fastapi import HTTPException, status
from app.core.config import settings


class PasswordUtil:
    """密码工具类"""
    
    pwd_context = None
    
    @classmethod
    def _init_pwd_context(cls):
        """初始化密码上下文"""
        if cls.pwd_context is None:
            try:
                cls.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            except Exception:
                # 如果bcrypt初始化失败，使用None标记
                cls.pwd_context = False
    
    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        """
        验证密码
        
        Args:
            plain_password: 明文密码
            hashed_password: 哈希密码
            
        Returns:
            是否匹配
        """
        cls._init_pwd_context()
        
        # 如果bcrypt可用，优先使用bcrypt验证
        if cls.pwd_context and cls.pwd_context != False:
            try:
                return cls.pwd_context.verify(plain_password, hashed_password)
            except Exception:
                pass
        
        # 如果bcrypt不可用或验证失败，尝试MD5验证
        import hashlib
        md5_hash = hashlib.md5(plain_password.encode()).hexdigest()
        return md5_hash == hashed_password
    
    @classmethod
    def get_password_hash(cls, password: str) -> str:
        """
        获取密码哈希
        
        Args:
            password: 明文密码
            
        Returns:
            哈希密码
        """
        cls._init_pwd_context()
        
        # 如果bcrypt可用，优先使用bcrypt
        if cls.pwd_context and cls.pwd_context != False:
            try:
                return cls.pwd_context.hash(password)
            except Exception:
                pass
        
        # 如果bcrypt不可用，使用MD5
        import hashlib
        return hashlib.md5(password.encode()).hexdigest()


class JWTUtil:
    """JWT工具类"""
    
    @classmethod
    def create_access_token(cls, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        创建访问令牌
        
        Args:
            data: 要编码的数据
            expires_delta: 过期时间增量
            
        Returns:
            JWT令牌
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
            
        to_encode.update({"exp": expire})
        to_encode.update({"iat": datetime.now(timezone.utc)})
        to_encode.update({"jti": str(uuid.uuid4())})  # JWT ID
        
        encoded_jwt = jwt.encode(
            to_encode, 
            settings.JWT_SECRET_KEY, 
            algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt
    
    @classmethod
    def decode_access_token(cls, token: str) -> Dict[str, Any]:
        """
        解码访问令牌
        
        Args:
            token: JWT令牌
            
        Returns:
            解码后的数据
            
        Raises:
            HTTPException: 令牌无效或过期
        """
        try:
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM]
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token已过期",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (jwt.InvalidTokenError, jwt.DecodeError, jwt.InvalidSignatureError, Exception) as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"令牌验证失败: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    @classmethod
    def get_token_expire_time(cls) -> int:
        """
        获取令牌过期时间（秒）
        
        Returns:
            过期时间秒数
        """
        return settings.JWT_EXPIRE_MINUTES * 60


class SessionUtil:
    """会话工具类"""
    
    @classmethod
    def generate_session_id(cls) -> str:
        """
        生成会话ID
        
        Returns:
            会话ID
        """
        return str(uuid.uuid4())
    
    @classmethod
    def generate_captcha_uuid(cls) -> str:
        """
        生成验证码UUID
        
        Returns:
            验证码UUID
        """
        return str(uuid.uuid4())


class SecurityUtil:
    """安全工具类"""
    
    @classmethod
    def check_password_strength(cls, password: str) -> bool:
        """
        检查密码强度
        
        Args:
            password: 密码
            
        Returns:
            是否符合强度要求
        """
        if len(password) < 6:
            return False
        
        # 可以添加更多密码强度检查规则
        # 例如：必须包含大小写字母、数字、特殊字符等
        
        return True
    
    @classmethod
    def sanitize_input(cls, input_str: str) -> str:
        """
        清理输入字符串，防止XSS攻击
        
        Args:
            input_str: 输入字符串
            
        Returns:
            清理后的字符串
        """
        if not input_str:
            return ""
        
        # 简单的XSS防护，实际项目中可能需要更复杂的处理
        dangerous_chars = ["<", ">", "\"", "'", "&", "script", "javascript"]
        cleaned = input_str
        
        for char in dangerous_chars:
            cleaned = cleaned.replace(char, "")
        
        return cleaned.strip()
    
    @classmethod
    def is_valid_email(cls, email: str) -> bool:
        """
        验证邮箱格式
        
        Args:
            email: 邮箱地址
            
        Returns:
            是否有效
        """
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @classmethod
    def is_valid_phone(cls, phone: str) -> bool:
        """
        验证手机号格式
        
        Args:
            phone: 手机号
            
        Returns:
            是否有效
        """
        import re
        pattern = r'^1[3-9]\d{9}$'
        return re.match(pattern, phone) is not None
