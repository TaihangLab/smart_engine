#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
杀死占用指定端口的进程
用于清理开发环境中占用端口的僵尸进程
"""

import argparse
import signal
import sys
import subprocess
from typing import List


def find_processes_by_port(port: int) -> List[tuple]:
    """
    查找占用指定端口的进程

    Args:
        port: 端口号

    Returns:
        [(pid, command)] 列表
    """
    try:
        # 使用 lsof 查找占用端口的进程
        result = subprocess.run(
            ['lsof', '-t', '-i', f':{port}'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0 or not result.stdout.strip():
            return []

        pids = result.stdout.strip().split('\n')
        processes = []

        for pid in pids:
            try:
                # 获取进程命令
                cmd_result = subprocess.run(
                    ['ps', '-p', pid, '-o', 'command='],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                command = cmd_result.stdout.strip()
                processes.append((int(pid), command))
            except (subprocess.TimeoutExpired, ValueError):
                continue

        return processes

    except (subprocess.TimeoutExpired, FileNotFoundError):
        # lsof 不可用时，尝试使用 netstat
        try:
            result = subprocess.run(
                ['netstat', '-anv', '-p', 'tcp'],
                capture_output=True,
                text=True,
                timeout=5
            )

            processes = []
            lines = result.stdout.split('\n')
            for line in lines:
                if f'.{port}' in line and 'LISTEN' in line:
                    parts = line.split()
                    if len(parts) > 0:
                        # netstat 输出格式可能不同，这里做简化处理
                        pass
            return processes

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []


def kill_process(pid: int, force: bool = False) -> bool:
    """
    杀死指定 PID 的进程

    Args:
        pid: 进程 ID
        force: 是否强制杀死 (SIGKILL)

    Returns:
        是否成功
    """
    try:
        sig = signal.SIGKILL if force else signal.SIGTERM
        os.kill(pid, sig)
        return True
    except ProcessLookupError:
        print(f"  ⚠️  进程 {pid} 不存在")
        return False
    except PermissionError:
        print(f"  ❌ 没有权限杀死进程 {pid}")
        return False
    except Exception as e:
        print(f"  ❌ 杀死进程 {pid} 失败: {e}")
        return False


def kill_port(port: int, force: bool = False, verbose: bool = True) -> int:
    """
    杀死占用指定端口的所有进程

    Args:
        port: 端口号
        force: 是否强制杀死
        verbose: 是否显示详细信息

    Returns:
        成功杀死的进程数量
    """
    if verbose:
        print(f"\n🔍 检查端口 {port}...")

    processes = find_processes_by_port(port)

    if not processes:
        if verbose:
            print(f"  ✅ 端口 {port} 没有被占用")
        return 0

    if verbose:
        print(f"  📋 端口 {port} 被以下进程占用:")
        for pid, command in processes:
            print(f"     - PID {pid}: {command[:60]}...")

    killed_count = 0
    for pid, command in processes:
        if verbose:
            print(f"  🔄 正在杀死进程 {pid}...")

        if kill_process(pid, force):
            if verbose:
                print(f"  ✅ 进程 {pid} 已被杀死")
            killed_count += 1

    return killed_count


def main():
    parser = argparse.ArgumentParser(
        description='杀死占用指定端口的进程',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 杀死占用 4001 端口的进程
  python kill_ports.py 4001

  # 杀死占用多个端口的进程
  python kill_ports.py 4001 4008 8000

  # 强制杀死进程
  python kill_ports.py 4001 -f

  # 安静模式
  python kill_ports.py 4001 -q
        """
    )

    parser.add_argument(
        'ports',
        type=int,
        nargs='+',
        help='要清理的端口号（可以指定多个）'
    )
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='强制杀死进程（使用 SIGKILL）'
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='安静模式，不输出详细信息'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("🔫 端口清理工具")
    print("=" * 60)

    total_killed = 0
    for port in args.ports:
        killed = kill_port(port, force=args.force, verbose=not args.quiet)
        total_killed += killed

    print("=" * 60)
    if args.quiet:
        print(f"✅ 共清理 {total_killed} 个进程")
    else:
        if total_killed > 0:
            print(f"✅ 成功清理 {total_killed} 个进程")
        else:
            print("✅ 没有需要清理的进程")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    import os
    sys.exit(main())
