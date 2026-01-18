#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
批量修复 API 路由中缺失的 request 参数

检测所有调用 user_context_service.get_validated_tenant_id(request, ...)
的函数，并添加缺失的 request: Request 参数
"""

import os
import re
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def find_functions_with_get_validated_tenant_id(file_path):
    """查找文件中所有调用 get_validated_tenant_id 的函数"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 找到所有调用 get_validated_tenant_id 的行号
    call_lines = []
    for i, line in enumerate(lines):
        if 'user_context_service.get_validated_tenant_id(request,' in line:
            call_lines.append(i + 1)  # 行号从 1 开始

    # 找到这些调用对应的函数
    functions = []
    for call_line in call_lines:
        # 向上查找函数定义
        func_name = None
        func_start_line = None
        has_request_param = False

        for i in range(call_line - 1, max(0, call_line - 50), -1):
            line = lines[i]

            # 检查是否找到函数定义
            if 'async def ' in line:
                func_name = line.strip()
                func_start_line = i + 1

                # 检查函数签名中是否有 request: Request
                for j in range(i, min(i + 20, len(lines))):
                    if ')' in lines[j]:
                        # 函数签名结束
                        signature = ''.join(lines[i:j+1])
                        if 'request: Request' in signature:
                            has_request_param = True
                        break
                break

        if func_name and not has_request_param:
            functions.append({
                'name': func_name,
                'line': func_start_line,
                'call_line': call_line
            })

    return functions


def fix_function_signature(file_path, func_info):
    """修复函数签名，添加 request: Request 参数"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 找到函数定义
    func_def_pattern = r'(async def\s+\w+\([^)]*)\)'
    matches = list(re.finditer(func_def_pattern, content))

    # 找到对应的函数
    target_match = None
    for match in matches:
        # 计算匹配位置对应的行号
        line_num = content[:match.start()].count('\n') + 1
        if line_num == func_info['line']:
            target_match = match
            break

    if not target_match:
        return False

    # 在函数参数列表中添加 request: Request
    # 策略：在第一个参数后面添加
    func_signature = target_match.group(1)

    # 检查是否已经有 request 参数
    if 'request: Request' in func_signature:
        return False

    # 找到第一个参数的位置
    params_start = func_signature.find('(')
    if params_start == -1:
        return False

    # 在左括号后添加 request: Request,
    # 但要在第一个参数之前，如果第一个参数是 self 或其他特殊参数
    params_part = func_signature[params_start + 1:]

    # 移除可能的空格和换行
    params_part = params_part.strip()

    # 构建新的函数签名
    if params_part and not params_part.startswith('db:'):
        # 在第一个参数前添加
        new_signature = func_signature[:params_start + 1] + f'request: Request, {params_part}'
    else:
        # 没有其他参数，直接添加
        new_signature = func_signature[:params_start + 1] + f'request: Request{params_part}'

    # 替换原函数签名
    new_content = content[:target_match.start()] + new_signature + ')' + content[target_match.end():]

    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return True


def scan_and_fix_api_routes():
    """扫描并修复所有 API 路由文件"""
    api_dir = '/Users/ray/IdeaProjects/taihang/smart_engine/app/api/rbac'

    # 所有需要检查的文件
    files_to_check = [
        'user_routes.py',
        'role_routes.py',
        'dept_routes.py',
        'permission_routes.py',
        'tenant_routes.py'
    ]

    total_fixed = 0

    for filename in files_to_check:
        file_path = os.path.join(api_dir, filename)

        if not os.path.exists(file_path):
            print(f"⚠️  文件不存在: {filename}")
            continue

        print(f"\n{'='*60}")
        print(f"检查文件: {filename}")
        print('='*60)

        functions = find_functions_with_get_validated_tenant_id(file_path)

        if not functions:
            print(f"✅ {filename}: 没有需要修复的函数")
            continue

        print(f"发现 {len(functions)} 个需要修复的函数:")
        for func in functions:
            print(f"  - 行 {func['line']}: {func['name']}")

        # 修复每个函数
        fixed_count = 0
        for func in functions:
            if fix_function_signature(file_path, func):
                print(f"  ✅ 修复成功: {func['name'].split('(')[0]}")
                fixed_count += 1
            else:
                print(f"  ❌ 修复失败: {func['name'].split('(')[0]}")

        total_fixed += fixed_count
        print(f"📊 {filename}: 修复了 {fixed_count}/{len(functions)} 个函数")

    print(f"\n{'='*60}")
    print(f"总计修复了 {total_fixed} 个函数")
    print('='*60)


if __name__ == '__main__':
    print("=" * 60)
    print("批量修复 API 路由中缺失的 request 参数")
    print("=" * 60)

    scan_and_fix_api_routes()

    print("\n✅ 完成！")
