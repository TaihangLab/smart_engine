"""
用户信息模型
用于承载从JWT Token中解析出的用户信息
"""
from typing import Optional
from pydantic import BaseModel, Field


class UserInfo(BaseModel):
    """
    用户信息模型
    对应JWT Token中的payload字段
    
    示例Token payload:
    {
        "loginType": "login",
        "loginId": "sys_user:1982714109680496641",
        "rnStr": "w4lcjEAESKeVOTGEeV9nStZMvio9O70A",
        "clientid": "02bb9cfe8d7844ecae8dbe62b1ba971a",
        "tenantId": "000000",
        "userId": 1982714109680496641,
        "userName": "ztsManager",
        "deptId": 1982713663419133953,
        "deptName": "中条山有色金属集团",
        "deptCategory": ""
    }
    """
    
    loginType: Optional[str] = Field(None, description="登录类型")
    loginId: Optional[str] = Field(None, description="登录ID")
    rnStr: Optional[str] = Field(None, description="随机字符串")
    clientid: Optional[str] = Field(None, description="客户端ID")
    tenantId: Optional[str] = Field(None, description="租户ID")
    userId: Optional[int] = Field(None, description="用户ID")
    userName: Optional[str] = Field(None, description="用户名")
    deptId: Optional[int] = Field(None, description="部门ID")
    deptName: Optional[str] = Field(None, description="部门名称")
    deptCategory: Optional[str] = Field(None, description="部门类别")
    
    class Config:
        """Pydantic配置"""
        # 允许通过属性名访问
        populate_by_name = True
        # JSON序列化示例
        json_schema_extra = {
            "example": {
                "loginType": "login",
                "loginId": "sys_user:1982714109680496641",
                "rnStr": "w4lcjEAESKeVOTGEeV9nStZMvio9O70A",
                "clientid": "02bb9cfe8d7844ecae8dbe62b1ba971a",
                "tenantId": "000000",
                "userId": 1982714109680496641,
                "userName": "ztsManager",
                "deptId": 1982713663419133953,
                "deptName": "中条山有色金属集团",
                "deptCategory": ""
            }
        }
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"UserInfo(userId={self.userId}, userName={self.userName}, tenantId={self.tenantId})"
    
    def __str__(self) -> str:
        """字符串表示"""
        return self.__repr__()
