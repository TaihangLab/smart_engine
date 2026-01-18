#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
生成 Base64 编码的认证 Token
用于测试和开发环境
"""

import base64
import json
import argparse
from typing import Dict, Any


def generate_token(
    user_id: str = "152120388603",
    user_name: str = "admin",
    tenant_id: str = "152120388608",
    tenant_name: str = "默认租户",
    company_name: str = "默认公司",
    company_code: str = "COMP-1",
    dept_id: str = "152120388605",
    dept_name: str = "系统部门",
    client_id: str = "02bb9cfe8d7844ecae8dbe62b1ba971a",
    **extra_fields
) -> str:
    """
    生成 Base64 编码的认证 Token

    Args:
        user_id: 用户 ID
        user_name: 用户名
        tenant_id: 租户 ID
        tenant_name: 租户名称
        company_name: 公司名称
        company_code: 公司代码
        dept_id: 部门 ID
        dept_name: 部门名称
        client_id: 客户端 ID
        **extra_fields: 额外的自定义字段

    Returns:
        Base64 编码的 token 字符串
    """
    # 构建 token 数据
    token_data = {
        "userId": user_id,
        "userName": user_name,
        "tenantId": tenant_id,
        "tenantName": tenant_name,
        "companyName": company_name,
        "companyCode": company_code,
        "deptId": dept_id,
        "deptName": dept_name,
        "clientid": client_id,
        **extra_fields
    }

    # 转换为 JSON 字符串
    json_str = json.dumps(token_data, ensure_ascii=False)

    # Base64 编码
    token_bytes = base64.b64encode(json_str.encode('utf-8'))
    token = token_bytes.decode('utf-8')

    return token


def decode_token(token: str) -> Dict[str, Any]:
    """
    解码 Base64 Token

    Args:
        token: Base64 编码的 token

    Returns:
        解码后的字典
    """
    try:
        decoded_bytes = base64.b64decode(token.encode('utf-8'))
        return json.loads(decoded_bytes.decode('utf-8'))
    except Exception as e:
        print(f"解码失败: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser(description='生成或解码 Base64 认证 Token')
    subparsers = parser.add_subparsers(dest='command', help='命令')

    # 生成 token 命令
    gen_parser = subparsers.add_parser('generate', help='生成 token')
    gen_parser.add_argument('--user-id', default='152120388603', help='用户 ID')
    gen_parser.add_argument('--user-name', default='admin', help='用户名')
    gen_parser.add_argument('--tenant-id', default='152120388608', help='租户 ID')
    gen_parser.add_argument('--tenant-name', default='默认租户', help='租户名称')
    gen_parser.add_argument('--company-name', default='默认公司', help='公司名称')
    gen_parser.add_argument('--company-code', default='COMP-1', help='公司代码')
    gen_parser.add_argument('--dept-id', default='152120388605', help='部门 ID')
    gen_parser.add_argument('--dept-name', default='系统部门', help='部门名称')
    gen_parser.add_argument('--client-id', default='02bb9cfe8d7844ecae8dbe62b1ba971a', help='客户端 ID')
    gen_parser.add_argument('--pretty', action='store_true', help='美化输出')

    # 解码 token 命令
    decode_parser = subparsers.add_parser('decode', help='解码 token')
    decode_parser.add_argument('token', help='要解码的 token')

    # 预设模板命令
    template_parser = subparsers.add_parser('template', help='使用预设模板生成 token')
    template_parser.add_argument('template', choices=['admin', 'user1', 'user2', 'tenant2'], help='模板名称')

    args = parser.parse_args()

    if args.command == 'generate':
        token = generate_token(
            user_id=args.user_id,
            user_name=args.user_name,
            tenant_id=args.tenant_id,
            tenant_name=args.tenant_name,
            company_name=args.company_name,
            company_code=args.company_code,
            dept_id=args.dept_id,
            dept_name=args.dept_name,
            client_id=args.client_id
        )

        if args.pretty:
            print("\n" + "=" * 60)
            print("生成的 Token:")
            print("=" * 60)
            print(token)
            print("\n" + "-" * 60)
            print("Token 内容:")
            print("-" * 60)
            print(json.dumps(decode_token(token), indent=2, ensure_ascii=False))
            print("\n" + "-" * 60)
            print("使用方式:")
            print("-" * 60)
            print(f"Authorization: Bearer {token}")
            print(f"clientid: {args.client_id}")
        else:
            print(token)

    elif args.command == 'decode':
        data = decode_token(args.token)
        print(json.dumps(data, indent=2, ensure_ascii=False))

    elif args.command == 'template':
        templates = {
            'admin': {
                'user_id': '152120388603',
                'user_name': 'admin',
                'tenant_id': '152120388608',
                'tenant_name': '默认租户',
                'company_name': '默认公司',
                'company_code': 'COMP-1',
                'dept_id': '152120388605',
                'dept_name': '系统管理部',
            },
            'user1': {
                'user_id': '152120388603',
                'user_name': 'zhangsan',
                'tenant_id': '1',
                'tenant_name': '默认租户',
                'company_name': '默认公司',
                'company_code': 'COMP-1',
                'dept_id': '2',
                'dept_name': '技术部',
            },
            'user2': {
                'user_id': '152120388603',
                'user_name': 'lisi',
                'tenant_id': '1',
                'tenant_name': '默认租户',
                'company_name': '默认公司',
                'company_code': 'COMP-1',
                'dept_id': '3',
                'dept_name': '运营部',
            },
            'tenant2': {
                'user_id': '100',
                'user_name': 'tenant2_admin',
                'tenant_id': '788999',
                'tenant_name': '租户2',
                'company_name': '租户2公司',
                'company_code': 'COMP-788999',
                'dept_id': '100',
                'dept_name': '租户2管理部',
            }
        }

        if args.template in templates:
            t = templates[args.template]
            token = generate_token(**t)
            print("\n" + "=" * 60)
            print(f"模板: {args.template}")
            print("=" * 60)
            print("\nToken:")
            print(token)
            print("\nToken 内容:")
            print(json.dumps(decode_token(token), indent=2, ensure_ascii=False))
            print("\n使用方式:")
            print(f"Authorization: Bearer {token}")
            print(f"clientid: {t.get('client_id', '02bb9cfe8d7844ecae8dbe62b1ba971a')}")
        else:
            print(f"未找到模板: {args.template}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
