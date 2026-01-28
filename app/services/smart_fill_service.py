#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
智能填充助手服务 (增强版)
为 RBAC 各页面提供 Mock 数据和验证规则（测试环境专用）

特性:
- 动态 Mock 数据生成
- 字段关联性建议
- 模糊搜索和自动完成
- 多场景数据模板
"""

import logging
import random
import string
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core.config import settings
from app.models.smart_fill import (
    SmartFillResponse,
    FieldSuggestion,
    FieldValidationRule,
    BatchSmartFillResponse
)

logger = logging.getLogger(__name__)


# ===========================================
# Mock 数据生成工具类
# ===========================================

class MockDataGenerator:
    """Mock 数据生成器"""

    # 中文姓氏
    SURNAMES = [
        "王", "李", "张", "刘", "陈", "杨", "黄", "赵", "周", "吴",
        "徐", "孙", "马", "胡", "朱", "郭", "何", "罗", "高", "林"
    ]

    # 中文名字
    NAMES = [
        "伟", "芳", "娜", "秀英", "敏", "静", "丽", "强", "磊", "军",
        "洋", "勇", "艳", "杰", "娟", "涛", "明", "超", "秀兰", "霞"
    ]

    # 部门名称模板
    DEPT_TEMPLATES = [
        "{prefix}部", "{prefix}中心", "{prefix}组", "{prefix}处"
    ]

    DEPT_PREFIXES = [
        "技术", "市场", "销售", "人力资源", "财务", "行政", "运营",
        "产品", "设计", "研发", "测试", "运维", "客服", "采购"
    ]

    # 岗位名称模板
    POSITION_TEMPLATES = [
        "{level}{role}", "{role}{level}", "高级{role}", "资深{role}"
    ]

    POSITION_ROLES = [
        "工程师", "经理", "专员", "主管", "总监", "架构师", "分析师",
        "设计师", "开发", "测试", "运维", "顾问", "助理"
    ]

    POSITION_LEVELS = [
        "初级", "中级", "高级", "资深", "专家", "首席"
    ]

    # 角色名称模板
    ROLE_TEMPLATES = [
        "{scope}{role}", "{role}", "{prefix}_{role}"
    ]

    ROLE_SCOPES = [
        "超级", "部门", "项目", "普通", "访客", "系统"
    ]

    ROLE_NAMES = [
        "管理员", "经理", "主管", "专员", "用户", "访客", "开发者",
        "测试员", "运维", "审计", "观察者"
    ]

    # 权限名称模板
    PERMISSION_TEMPLATES = [
        "{resource}:{action}", "{resource}:{action}:{scope}"
    ]

    PERMISSION_RESOURCES = [
        "user", "role", "dept", "position", "tenant", "permission",
        "camera", "task", "alert", "report", "system", "config"
    ]

    PERMISSION_ACTIONS = [
        "view", "create", "edit", "delete", "manage", "export", "import", "approve"
    ]

    @classmethod
    def generate_user_name(cls, seed: Optional[int] = None) -> str:
        """生成随机用户名"""
        if seed is not None:
            random.seed(seed)
        name = f"user_{random.randint(1000, 9999)}"
        return name

    @classmethod
    def generate_nick_name(cls, seed: Optional[int] = None) -> str:
        """生成随机中文昵称"""
        if seed is not None:
            random.seed(seed)
        surname = random.choice(cls.SURNAMES)
        name = random.choice(cls.NAMES)
        return f"{surname}{name}"

    @classmethod
    def generate_phone(cls, seed: Optional[int] = None) -> str:
        """生成随机手机号"""
        if seed is not None:
            random.seed(seed)
        prefixes = ["130", "131", "132", "133", "135", "136", "137",
                   "138", "139", "150", "151", "152", "153", "155",
                   "156", "157", "158", "159", "186", "187", "188", "189"]
        prefix = random.choice(prefixes)
        suffix = ''.join([str(random.randint(0, 9)) for _ in range(8)])
        return f"{prefix}{suffix}"

    @classmethod
    def generate_email(cls, user_name: Optional[str] = None, seed: Optional[int] = None) -> str:
        """生成随机邮箱"""
        if seed is not None:
            random.seed(seed)
        if not user_name:
            user_name = cls.generate_user_name()

        domains = ["example.com", "test.com", "demo.com", "mail.com"]
        domain = random.choice(domains)
        return f"{user_name}@{domain}"

    @classmethod
    def generate_password(cls, strength: str = "strong") -> str:
        """
        生成随机密码

        Args:
            strength: 密码强度 (weak/medium/strong)
        """
        if strength == "weak":
            # 8位数字
            return ''.join([str(random.randint(0, 9)) for _ in range(8)])
        elif strength == "medium":
            # 8位字母数字混合
            chars = string.ascii_letters + string.digits
            return ''.join([random.choice(chars) for _ in range(8)])
        else:
            # 强密码：大小写字母+数字+特殊字符
            lowercase = random.choice(string.ascii_lowercase)
            uppercase = random.choice(string.ascii_uppercase)
            digit = random.choice(string.digits)
            special = random.choice("!@#$%&*")
            remaining = ''.join([random.choice(string.ascii_letters + string.digits + "!@#$%&*")
                               for _ in range(8)])
            password = list(lowercase + uppercase + digit + special + remaining)
            random.shuffle(password)
            return ''.join(password)

    @classmethod
    def generate_dept_name(cls, seed: Optional[int] = None) -> str:
        """生成随机部门名称"""
        if seed is not None:
            random.seed(seed)
        template = random.choice(cls.DEPT_TEMPLATES)
        prefix = random.choice(cls.DEPT_PREFIXES)
        return template.format(prefix=prefix)

    @classmethod
    def generate_position_name(cls, seed: Optional[int] = None) -> str:
        """生成随机岗位名称"""
        if seed is not None:
            random.seed(seed)
        template = random.choice(cls.POSITION_TEMPLATES)
        if "{level}" in template and "{role}" in template:
            level = random.choice(cls.POSITION_LEVELS)
            role = random.choice(cls.POSITION_ROLES)
            return template.format(level=level, role=role)
        else:
            role = random.choice(cls.POSITION_ROLES)
            return template.format(role=role)

    @classmethod
    def generate_role_name(cls, seed: Optional[int] = None) -> str:
        """生成随机角色名称"""
        if seed is not None:
            random.seed(seed)
        template = random.choice(cls.ROLE_TEMPLATES)
        if "{scope}" in template and "{role}" in template:
            scope = random.choice(cls.ROLE_SCOPES)
            role = random.choice(cls.ROLE_NAMES)
            return template.format(scope=scope, role=role)
        elif "{prefix}" in template and "{role}" in template:
            prefix = random.choice(cls.ROLE_SCOPES)
            role = random.choice(cls.ROLE_NAMES)
            return template.format(prefix=prefix, role=role)
        else:
            role = random.choice(cls.ROLE_NAMES)
            return template.format(role=role)

    @classmethod
    def generate_role_code(cls, role_name: Optional[str] = None, seed: Optional[int] = None) -> str:
        """生成随机角色编码"""
        if seed is not None:
            random.seed(seed)
        if not role_name:
            role_name = cls.generate_role_name()
        # 将中文角色名转换为拼音风格的编码
        code_map = {
            "超级": "super", "部门": "dept", "项目": "project", "普通": "common",
            "访客": "guest", "系统": "system", "管理员": "admin", "经理": "manager",
            "主管": "supervisor", "专员": "specialist", "用户": "user", "开发者": "developer",
            "测试员": "tester", "运维": "ops", "审计": "auditor", "观察者": "observer"
        }
        for chinese, english in code_map.items():
            role_name = role_name.replace(chinese, english)
        return role_name.lower().replace(" ", "_")

    @classmethod
    def generate_permission_name(cls, seed: Optional[int] = None) -> str:
        """生成随机权限名称"""
        if seed is not None:
            random.seed(seed)
        resource = random.choice(cls.PERMISSION_RESOURCES)
        action = random.choice(cls.PERMISSION_ACTIONS)
        action_map = {
            "view": "查看", "create": "创建", "edit": "编辑", "delete": "删除",
            "manage": "管理", "export": "导出", "import": "导入", "approve": "审批"
        }
        resource_map = {
            "user": "用户", "role": "角色", "dept": "部门", "position": "岗位",
            "tenant": "租户", "permission": "权限", "camera": "摄像头",
            "task": "任务", "alert": "预警", "report": "报表", "system": "系统", "config": "配置"
        }
        return f"{resource_map.get(resource, resource)}{action_map.get(action, action)}"

    @classmethod
    def generate_permission_code(cls, seed: Optional[int] = None) -> str:
        """生成随机权限编码"""
        if seed is not None:
            random.seed(seed)
        resource = random.choice(cls.PERMISSION_RESOURCES)
        action = random.choice(cls.PERMISSION_ACTIONS)
        return f"{resource}:{action}"

    @classmethod
    def generate_position_code(cls, position_name: Optional[str] = None, seed: Optional[int] = None) -> str:
        """生成随机岗位编码"""
        if seed is not None:
            random.seed(seed)
        if not position_name:
            position_name = cls.generate_position_name()
        # 简化岗位编码生成
        code_map = {
            "工程师": "engineer", "经理": "manager", "专员": "specialist",
            "主管": "supervisor", "总监": "director", "架构师": "architect",
            "分析师": "analyst", "设计师": "designer", "开发": "developer",
            "测试": "tester", "运维": "ops", "顾问": "consultant", "助理": "assistant"
        }
        for chinese, english in code_map.items():
            position_name = position_name.replace(chinese, english)
        # 移除前缀
        for level in ["初级", "中级", "高级", "资深", "专家", "首席"]:
            position_name = position_name.replace(level, "")
        return position_name.lower().replace(" ", "_")


# ===========================================
# 字段关联建议提供器
# ===========================================

class FieldRelationProvider:
    """字段关联建议提供器"""

    # 部门-岗位关联
    DEPT_POSITION_RELATIONS = {
        "技术部": ["工程师", "架构师", "开发", "测试", "运维"],
        "市场部": ["经理", "专员", "顾问", "分析师"],
        "销售部": ["经理", "专员", "主管", "代表"],
        "人力资源部": ["经理", "专员", "主管", "助理"],
        "财务部": ["经理", "专员", "会计", "分析师"],
        "行政部": ["经理", "专员", "助理", "主管"],
        "运营部": ["经理", "专员", "主管", "分析师"],
        "产品部": ["经理", "专员", "设计师", "主管"],
        "设计部": ["设计师", "主管", "总监", "助理"],
        "研发部": ["工程师", "架构师", "开发", "测试"],
        "测试部": ["测试员", "主管", "工程师", "经理"],
        "运维部": ["运维", "工程师", "主管", "总监"],
        "客服部": ["专员", "主管", "经理", "代表"],
        "采购部": ["专员", "主管", "经理", "助理"]
    }

    # 角色-权限关联
    ROLE_PERMISSION_RELATIONS = {
        "超级管理员": ["user:*", "role:*", "dept:*", "position:*", "system:*"],
        "部门主管": ["user:view", "user:edit", "dept:view", "task:*"],
        "普通用户": ["user:view", "task:view", "report:view"],
        "访客": ["user:view"],
        "运维人员": ["system:*", "task:*", "alert:*"],
        "开发者": ["task:*", "camera:*", "skill:*"]
    }

    @classmethod
    def get_related_positions(cls, dept_name: str) -> List[str]:
        """根据部门名称获取推荐的岗位列表"""
        # 模糊匹配部门名称
        for key, positions in cls.DEPT_POSITION_RELATIONS.items():
            if key in dept_name or dept_name in key:
                return positions
        # 默认返回通用岗位
        return ["专员", "主管", "经理"]

    @classmethod
    def get_related_permissions(cls, role_name: str) -> List[str]:
        """根据角色名称获取推荐的权限列表"""
        # 模糊匹配角色名称
        for key, permissions in cls.ROLE_PERMISSION_RELATIONS.items():
            if key in role_name or role_name in key:
                return permissions
        # 默认返回基础权限
        return ["user:view", "task:view"]


# ===========================================
# 智能填充助手服务 (增强版)
# ===========================================

class SmartFillService:
    """智能填充助手服务 (增强版)"""

    # 页面类型配置
    PAGE_TYPES = {
        "user": "用户管理",
        "role": "角色管理",
        "dept": "部门管理",
        "position": "岗位管理",
        "tenant": "租户管理",
        "permission": "权限管理"
    }

    # 字段标签映射
    FIELD_LABELS = {
        "user": {
            "user_name": "用户名",
            "nick_name": "昵称",
            "phone": "手机号",
            "email": "邮箱",
            "password": "密码",
            "gender": "性别",
            "status": "状态",
            "dept_id": "所属部门",
            "position_id": "岗位"
        },
        "role": {
            "role_name": "角色名称",
            "role_code": "角色编码",
            "data_scope": "数据权限范围",
            "status": "状态",
            "sort_order": "显示顺序"
        },
        "dept": {
            "dept_name": "部门名称",
            "parent_id": "父部门",
            "status": "状态",
            "sort_order": "显示顺序"
        },
        "position": {
            "position_name": "岗位名称",
            "position_code": "岗位编码",
            "status": "状态",
            "sort_order": "显示顺序"
        },
        "tenant": {
            "tenant_name": "租户名称",
            "tenant_code": "租户编码",
            "contact_name": "联系人",
            "contact_phone": "联系电话",
            "status": "状态"
        },
        "permission": {
            "permission_name": "权限名称",
            "permission_code": "权限编码",
            "permission_type": "权限类型",
            "status": "状态",
            "sort_order": "显示顺序"
        }
    }

    # 验证规则配置
    VALIDATION_RULES = {
        "user": [
            FieldValidationRule(
                field_name="user_name",
                required=True,
                min_length=2,
                max_length=64,
                pattern=r"^[a-zA-Z0-9_]+$"
            ),
            FieldValidationRule(
                field_name="nick_name",
                required=True,
                min_length=2,
                max_length=64
            ),
            FieldValidationRule(
                field_name="phone",
                required=False,
                pattern=r"^1[3-9]\d{9}$"
            ),
            FieldValidationRule(
                field_name="email",
                required=False,
                pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            ),
            FieldValidationRule(
                field_name="password",
                required=True,
                min_length=8,
                max_length=100,
                pattern=r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
            ),
            FieldValidationRule(
                field_name="gender",
                required=False,
                allowed_values=[0, 1, 2]
            ),
            FieldValidationRule(
                field_name="status",
                required=True,
                allowed_values=[0, 1]
            )
        ],
        "role": [
            FieldValidationRule(
                field_name="role_name",
                required=True,
                min_length=2,
                max_length=64
            ),
            FieldValidationRule(
                field_name="role_code",
                required=True,
                min_length=2,
                max_length=64,
                pattern=r"^[a-zA-Z0-9_]+$"
            ),
            FieldValidationRule(
                field_name="data_scope",
                required=True,
                allowed_values=[1, 2, 3, 4]
            ),
            FieldValidationRule(
                field_name="status",
                required=True,
                allowed_values=[0, 1]
            )
        ],
        "dept": [
            FieldValidationRule(
                field_name="dept_name",
                required=True,
                min_length=2,
                max_length=64
            ),
            FieldValidationRule(
                field_name="parent_id",
                required=False
            ),
            FieldValidationRule(
                field_name="status",
                required=True,
                allowed_values=[0, 1]
            )
        ],
        "position": [
            FieldValidationRule(
                field_name="position_name",
                required=True,
                min_length=2,
                max_length=64
            ),
            FieldValidationRule(
                field_name="position_code",
                required=True,
                min_length=2,
                max_length=64,
                pattern=r"^[a-zA-Z0-9_]+$"
            ),
            FieldValidationRule(
                field_name="status",
                required=True,
                allowed_values=[0, 1]
            )
        ],
        "tenant": [
            FieldValidationRule(
                field_name="tenant_name",
                required=True,
                min_length=2,
                max_length=64
            ),
            FieldValidationRule(
                field_name="tenant_code",
                required=True,
                min_length=2,
                max_length=64,
                pattern=r"^[a-zA-Z0-9_]+$"
            ),
            FieldValidationRule(
                field_name="contact_phone",
                required=False,
                pattern=r"^1[3-9]\d{9}$"
            ),
            FieldValidationRule(
                field_name="status",
                required=True,
                allowed_values=[0, 1]
            )
        ],
        "permission": [
            FieldValidationRule(
                field_name="permission_name",
                required=True,
                min_length=2,
                max_length=64
            ),
            FieldValidationRule(
                field_name="permission_code",
                required=True,
                min_length=2,
                max_length=64,
                pattern=r"^[a-zA-Z0-9:_-]+$"
            ),
            FieldValidationRule(
                field_name="permission_type",
                required=True,
                allowed_values=["menu", "button", "api"]
            ),
            FieldValidationRule(
                field_name="status",
                required=True,
                allowed_values=[0, 1]
            )
        ]
    }

    @classmethod
    def is_enabled(cls) -> bool:
        """检查智能填充助手是否启用"""
        return settings.SMART_FILL_ENABLED

    @classmethod
    def get_smart_fill(
        cls,
        page_type: str,
        include_validation: bool = True,
        context: Optional[Dict[str, Any]] = None,
        count: int = 1
    ) -> SmartFillResponse:
        """
        获取指定页面的智能填充建议

        Args:
            page_type: 页面类型 (user/role/dept/position/tenant/permission)
            include_validation: 是否包含验证规则
            context: 上下文信息（用于字段关联建议）
            count: 生成建议的数量

        Returns:
            SmartFillResponse: 智能填充响应
        """
        if not cls.is_enabled():
            logger.warning("智能填充助手未启用")
            return SmartFillResponse(
                page_name=cls.PAGE_TYPES.get(page_type, page_type),
                page_type=page_type,
                suggestions=[],
                validation_rules=[],
                auto_fill_enabled=False
            )

        if page_type not in cls.PAGE_TYPES:
            logger.error(f"不支持的页面类型: {page_type}")
            return SmartFillResponse(
                page_name=cls.PAGE_TYPES.get(page_type, page_type),
                page_type=page_type,
                suggestions=[],
                validation_rules=[],
                auto_fill_enabled=False
            )

        # 生成字段填充建议
        suggestions = cls._generate_suggestions(page_type, context, count)

        # 获取验证规则
        validation_rules = []
        if include_validation:
            validation_rules = cls.VALIDATION_RULES.get(page_type, [])

        return SmartFillResponse(
            page_name=cls.PAGE_TYPES[page_type],
            page_type=page_type,
            suggestions=suggestions,
            validation_rules=validation_rules,
            auto_fill_enabled=True
        )

    @classmethod
    def _generate_suggestions(
        cls,
        page_type: str,
        context: Optional[Dict[str, Any]] = None,
        count: int = 1
    ) -> List[FieldSuggestion]:
        """
        生成字段填充建议

        Args:
            page_type: 页面类型
            context: 上下文信息
            count: 生成建议的数量

        Returns:
            List[FieldSuggestion]: 字段建议列表
        """
        suggestions = []
        field_labels = cls.FIELD_LABELS.get(page_type, {})

        # 根据页面类型生成字段建议
        if page_type == "user":
            suggestions.extend(cls._generate_user_suggestions(field_labels, context, count))
        elif page_type == "role":
            suggestions.extend(cls._generate_role_suggestions(field_labels, count))
        elif page_type == "dept":
            suggestions.extend(cls._generate_dept_suggestions(field_labels, count))
        elif page_type == "position":
            suggestions.extend(cls._generate_position_suggestions(field_labels, count))
        elif page_type == "tenant":
            suggestions.extend(cls._generate_tenant_suggestions(field_labels, count))
        elif page_type == "permission":
            suggestions.extend(cls._generate_permission_suggestions(field_labels, count))

        return suggestions

    @classmethod
    def _generate_user_suggestions(
        cls,
        field_labels: Dict[str, str],
        context: Optional[Dict[str, Any]],
        count: int
    ) -> List[FieldSuggestion]:
        """生成用户表单建议"""
        suggestions = []

        # 生成用户名
        user_name = MockDataGenerator.generate_user_name()
        suggestions.append(FieldSuggestion(
            field_name="user_name",
            label=field_labels.get("user_name", "用户名"),
            suggested_value=user_name,
            confidence=0.9,
            hint="建议使用英文字母、数字和下划线"
        ))

        # 生成昵称
        nick_name = MockDataGenerator.generate_nick_name()
        suggestions.append(FieldSuggestion(
            field_name="nick_name",
            label=field_labels.get("nick_name", "昵称"),
            suggested_value=nick_name,
            confidence=0.9,
            hint="建议使用2-64个字符"
        ))

        # 生成手机号
        phone = MockDataGenerator.generate_phone()
        suggestions.append(FieldSuggestion(
            field_name="phone",
            label=field_labels.get("phone", "手机号"),
            suggested_value=phone,
            confidence=0.8,
            hint="请输入有效的手机号码"
        ))

        # 生成邮箱
        email = MockDataGenerator.generate_email(user_name)
        suggestions.append(FieldSuggestion(
            field_name="email",
            label=field_labels.get("email", "邮箱"),
            suggested_value=email,
            confidence=0.8,
            hint="请输入有效的邮箱地址"
        ))

        # 生成密码
        password = MockDataGenerator.generate_password("strong")
        suggestions.append(FieldSuggestion(
            field_name="password",
            label=field_labels.get("password", "密码"),
            suggested_value=password,
            confidence=0.7,
            hint="建议使用强密码，包含大小写字母、数字和特殊字符"
        ))

        # 性别
        suggestions.append(FieldSuggestion(
            field_name="gender",
            label=field_labels.get("gender", "性别"),
            suggested_value=0,
            confidence=1.0,
            hint="0-未知, 1-男, 2-女"
        ))

        # 状态
        suggestions.append(FieldSuggestion(
            field_name="status",
            label=field_labels.get("status", "状态"),
            suggested_value=0,
            confidence=1.0,
            hint="0-启用, 1-禁用"
        ))

        # 根据上下文生成关联建议
        if context and "dept_name" in context:
            related_positions = FieldRelationProvider.get_related_positions(context["dept_name"])
            if related_positions:
                suggestions.append(FieldSuggestion(
                    field_name="position_hint",
                    label="岗位建议",
                    suggested_value=related_positions[0],
                    confidence=0.7,
                    hint=f"根据部门 '{context['dept_name']}' 推荐的岗位: {', '.join(related_positions[:3])}"
                ))

        return suggestions

    @classmethod
    def _generate_role_suggestions(
        cls,
        field_labels: Dict[str, str],
        count: int
    ) -> List[FieldSuggestion]:
        """生成角色表单建议"""
        suggestions = []

        # 生成角色名称
        role_name = MockDataGenerator.generate_role_name()
        suggestions.append(FieldSuggestion(
            field_name="role_name",
            label=field_labels.get("role_name", "角色名称"),
            suggested_value=role_name,
            confidence=0.9,
            hint="建议使用2-64个字符"
        ))

        # 生成角色编码
        role_code = MockDataGenerator.generate_role_code(role_name)
        suggestions.append(FieldSuggestion(
            field_name="role_code",
            label=field_labels.get("role_code", "角色编码"),
            suggested_value=role_code,
            confidence=0.9,
            hint="建议使用英文字母、数字和下划线"
        ))

        # 数据权限范围
        suggestions.append(FieldSuggestion(
            field_name="data_scope",
            label=field_labels.get("data_scope", "数据权限范围"),
            suggested_value=1,
            confidence=0.8,
            hint="1-全部, 2-自定义, 3-本部门, 4-本部门及以下"
        ))

        # 状态
        suggestions.append(FieldSuggestion(
            field_name="status",
            label=field_labels.get("status", "状态"),
            suggested_value=0,
            confidence=1.0,
            hint="0-启用, 1-禁用"
        ))

        # 显示顺序
        suggestions.append(FieldSuggestion(
            field_name="sort_order",
            label=field_labels.get("sort_order", "显示顺序"),
            suggested_value=0,
            confidence=1.0,
            hint="数字越小越靠前"
        ))

        return suggestions

    @classmethod
    def _generate_dept_suggestions(
        cls,
        field_labels: Dict[str, str],
        count: int
    ) -> List[FieldSuggestion]:
        """生成部门表单建议"""
        suggestions = []

        # 生成部门名称
        dept_name = MockDataGenerator.generate_dept_name()
        suggestions.append(FieldSuggestion(
            field_name="dept_name",
            label=field_labels.get("dept_name", "部门名称"),
            suggested_value=dept_name,
            confidence=0.9,
            hint="建议使用2-64个字符"
        ))

        # 父部门
        suggestions.append(FieldSuggestion(
            field_name="parent_id",
            label=field_labels.get("parent_id", "父部门"),
            suggested_value=0,
            confidence=0.8,
            hint="0表示根部门"
        ))

        # 状态
        suggestions.append(FieldSuggestion(
            field_name="status",
            label=field_labels.get("status", "状态"),
            suggested_value=0,
            confidence=1.0,
            hint="0-启用, 1-禁用"
        ))

        # 显示顺序
        suggestions.append(FieldSuggestion(
            field_name="sort_order",
            label=field_labels.get("sort_order", "显示顺序"),
            suggested_value=0,
            confidence=1.0,
            hint="数字越小越靠前"
        ))

        return suggestions

    @classmethod
    def _generate_position_suggestions(
        cls,
        field_labels: Dict[str, str],
        count: int
    ) -> List[FieldSuggestion]:
        """生成岗位表单建议"""
        suggestions = []

        # 生成岗位名称
        position_name = MockDataGenerator.generate_position_name()
        suggestions.append(FieldSuggestion(
            field_name="position_name",
            label=field_labels.get("position_name", "岗位名称"),
            suggested_value=position_name,
            confidence=0.9,
            hint="建议使用2-64个字符"
        ))

        # 生成岗位编码
        position_code = MockDataGenerator.generate_position_code(position_name)
        suggestions.append(FieldSuggestion(
            field_name="position_code",
            label=field_labels.get("position_code", "岗位编码"),
            suggested_value=position_code,
            confidence=0.9,
            hint="建议使用英文字母、数字和下划线"
        ))

        # 状态
        suggestions.append(FieldSuggestion(
            field_name="status",
            label=field_labels.get("status", "状态"),
            suggested_value=0,
            confidence=1.0,
            hint="0-启用, 1-禁用"
        ))

        # 显示顺序
        suggestions.append(FieldSuggestion(
            field_name="sort_order",
            label=field_labels.get("sort_order", "显示顺序"),
            suggested_value=0,
            confidence=1.0,
            hint="数字越小越靠前"
        ))

        return suggestions

    @classmethod
    def _generate_tenant_suggestions(
        cls,
        field_labels: Dict[str, str],
        count: int
    ) -> List[FieldSuggestion]:
        """生成租户表单建议"""
        suggestions = []

        # 租户名称
        suggestions.append(FieldSuggestion(
            field_name="tenant_name",
            label=field_labels.get("tenant_name", "租户名称"),
            suggested_value=f"测试租户{random.randint(1000, 9999)}",
            confidence=0.9,
            hint="建议使用2-64个字符"
        ))

        # 租户编码
        suggestions.append(FieldSuggestion(
            field_name="tenant_code",
            label=field_labels.get("tenant_code", "租户编码"),
            suggested_value=f"tenant_{random.randint(1000, 9999)}",
            confidence=0.9,
            hint="建议使用英文字母、数字和下划线"
        ))

        # 联系人
        suggestions.append(FieldSuggestion(
            field_name="contact_name",
            label=field_labels.get("contact_name", "联系人"),
            suggested_value=MockDataGenerator.generate_nick_name(),
            confidence=0.8,
            hint=None
        ))

        # 联系电话
        suggestions.append(FieldSuggestion(
            field_name="contact_phone",
            label=field_labels.get("contact_phone", "联系电话"),
            suggested_value=MockDataGenerator.generate_phone(),
            confidence=0.8,
            hint="请输入有效的手机号码"
        ))

        # 状态
        suggestions.append(FieldSuggestion(
            field_name="status",
            label=field_labels.get("status", "状态"),
            suggested_value=0,
            confidence=1.0,
            hint="0-启用, 1-禁用"
        ))

        return suggestions

    @classmethod
    def _generate_permission_suggestions(
        cls,
        field_labels: Dict[str, str],
        count: int
    ) -> List[FieldSuggestion]:
        """生成权限表单建议"""
        suggestions = []

        # 生成权限名称
        permission_name = MockDataGenerator.generate_permission_name()
        suggestions.append(FieldSuggestion(
            field_name="permission_name",
            label=field_labels.get("permission_name", "权限名称"),
            suggested_value=permission_name,
            confidence=0.9,
            hint="建议使用2-64个字符"
        ))

        # 生成权限编码
        permission_code = MockDataGenerator.generate_permission_code()
        suggestions.append(FieldSuggestion(
            field_name="permission_code",
            label=field_labels.get("permission_code", "权限编码"),
            suggested_value=permission_code,
            confidence=0.9,
            hint="格式: resource:action，如 user:view"
        ))

        # 权限类型
        permission_types = ["menu", "button", "api"]
        suggestions.append(FieldSuggestion(
            field_name="permission_type",
            label=field_labels.get("permission_type", "权限类型"),
            suggested_value=random.choice(permission_types),
            confidence=0.8,
            hint="menu-菜单, button-按钮, api-接口"
        ))

        # 状态
        suggestions.append(FieldSuggestion(
            field_name="status",
            label=field_labels.get("status", "状态"),
            suggested_value=0,
            confidence=1.0,
            hint="0-启用, 1-禁用"
        ))

        # 显示顺序
        suggestions.append(FieldSuggestion(
            field_name="sort_order",
            label=field_labels.get("sort_order", "显示顺序"),
            suggested_value=0,
            confidence=1.0,
            hint="数字越小越靠前"
        ))

        return suggestions

    @classmethod
    def get_batch_smart_fill(
        cls,
        page_types: List[str],
        include_validation: bool = True,
        count: int = 1
    ) -> BatchSmartFillResponse:
        """
        批量获取多个页面的智能填充建议

        Args:
            page_types: 页面类型列表
            include_validation: 是否包含验证规则
            count: 每个页面生成建议的数量

        Returns:
            BatchSmartFillResponse: 批量智能填充响应
        """
        items = {}

        for page_type in page_types:
            response = cls.get_smart_fill(page_type, include_validation, count=count)
            items[page_type] = response

        return BatchSmartFillResponse(items=items)

    @classmethod
    def get_supported_pages(cls) -> Dict[str, str]:
        """
        获取支持的页面列表

        Returns:
            Dict[str, str]: 页面类型到页面名称的映射
        """
        return cls.PAGE_TYPES.copy()

    @classmethod
    def search_field_suggestions(
        cls,
        page_type: str,
        field_name: str,
        query: str,
        limit: int = 10
    ) -> List[FieldSuggestion]:
        """
        搜索字段建议（自动完成功能）

        Args:
            page_type: 页面类型
            field_name: 字段名称
            query: 搜索关键词
            limit: 返回结果数量限制

        Returns:
            List[FieldSuggestion]: 匹配的字段建议列表
        """
        if not cls.is_enabled():
            return []

        suggestions = []
        field_labels = cls.FIELD_LABELS.get(page_type, {})

        # 根据字段类型生成匹配的建议
        if field_name == "user_name":
            for i in range(min(limit, 5)):
                suggestions.append(FieldSuggestion(
                    field_name=field_name,
                    label=field_labels.get(field_name, field_name),
                    suggested_value=f"{query}_{random.randint(1000, 9999)}" if query else MockDataGenerator.generate_user_name(),
                    confidence=0.8,
                    hint="用户名建议"
                ))
        elif field_name == "nick_name":
            for i in range(min(limit, 5)):
                suggestions.append(FieldSuggestion(
                    field_name=field_name,
                    label=field_labels.get(field_name, field_name),
                    suggested_value=query if query else MockDataGenerator.generate_nick_name(),
                    confidence=0.8,
                    hint="昵称建议"
                ))
        elif field_name == "dept_name":
            for prefix in MockDataGenerator.DEPT_PREFIXES:
                if not query or query in prefix:
                    suggestions.append(FieldSuggestion(
                        field_name=field_name,
                        label=field_labels.get(field_name, field_name),
                        suggested_value=f"{prefix}部",
                        confidence=0.7,
                        hint="部门名称建议"
                    ))
                    if len(suggestions) >= limit:
                        break
        elif field_name == "position_name":
            for role in MockDataGenerator.POSITION_ROLES:
                if not query or query in role:
                    suggestions.append(FieldSuggestion(
                        field_name=field_name,
                        label=field_labels.get(field_name, field_name),
                        suggested_value=role,
                        confidence=0.7,
                        hint="岗位名称建议"
                    ))
                    if len(suggestions) >= limit:
                        break

        return suggestions


smart_fill_service = SmartFillService()
