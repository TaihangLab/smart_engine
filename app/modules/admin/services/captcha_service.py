"""
验证码服务
"""
import io
import base64
import random
import string
from typing import Tuple
from PIL import Image, ImageDraw, ImageFont
from app.modules.admin.utils.auth_util import SessionUtil


class CaptchaService:
    """验证码服务类"""
    
    @classmethod
    def generate_captcha(cls, width: int = 120, height: int = 40) -> Tuple[str, str, str]:
        """
        生成验证码
        
        Args:
            width: 图片宽度
            height: 图片高度
            
        Returns:
            (验证码文本, 验证码图片base64, UUID)
        """
        # 生成随机验证码文本
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        
        # 创建图片
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)
        
        # 尝试使用系统字体，如果失败则使用默认字体
        try:
            # 在Windows系统上尝试使用Arial字体
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            try:
                # 在Linux系统上尝试使用DejaVu字体
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
            except:
                # 使用PIL默认字体
                font = ImageFont.load_default()
        
        # 绘制验证码文本
        text_width = draw.textlength(code, font=font)
        text_height = 20
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        # 为每个字符添加随机颜色和位置偏移
        for i, char in enumerate(code):
            char_x = x + i * (text_width // len(code))
            char_y = y + random.randint(-5, 5)
            color = (
                random.randint(0, 100),
                random.randint(0, 100),
                random.randint(0, 100)
            )
            draw.text((char_x, char_y), char, fill=color, font=font)
        
        # 添加干扰线
        for _ in range(3):
            start = (random.randint(0, width), random.randint(0, height))
            end = (random.randint(0, width), random.randint(0, height))
            draw.line([start, end], fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
        
        # 添加噪点
        for _ in range(50):
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            draw.point((x, y), fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
        
        # 将图片转换为base64
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        # 生成UUID
        uuid = SessionUtil.generate_captcha_uuid()
        
        return code, f"data:image/png;base64,{img_base64}", uuid
    
    @classmethod
    def verify_captcha(cls, user_code: str, stored_code: str) -> bool:
        """
        验证验证码
        
        Args:
            user_code: 用户输入的验证码
            stored_code: 存储的验证码
            
        Returns:
            是否验证成功
        """
        if not user_code or not stored_code:
            return False
        
        return user_code.upper() == stored_code.upper()
