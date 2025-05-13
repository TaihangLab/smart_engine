import logging
import sys
import os

# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.wvp_client import WVPClient

# 直接测试功能
def main():
    """测试WVP客户端的通用channelId功能"""
    print("开始测试WVP客户端的通用channelId功能...")
    
    # 创建WVP客户端实例
    client = WVPClient()
    
    # 测试1: 获取国标设备通用channelId
    print("\n1. 测试国标设备的通用channelId获取")
    try:
        channel_id = client.get_universal_channel_id(
            'gb28181',
            device_id='34020000001320000001',
            channel_id='34020000001320000001'
        )
    except Exception as e:
        print(f"测试失败: {str(e)}")
    
    # 测试2: 获取推流设备通用channelId
    print("\n2. 测试推流设备的通用channelId获取")
    try:
        channel_id = client.get_universal_channel_id(
            'push_stream',
            app='live',
            stream='construction'
        )
        print(f"推流设备通用channelId: {channel_id}")
    except Exception as e:
        print(f"测试失败: {str(e)}")
    
    # 测试3: 获取代理流设备通用channelId
    print("\n3. 测试代理流设备的通用channelId获取")
    try:
        channel_id = client.get_universal_channel_id(
            'proxy_stream',
            app='app',
            stream='test'
        )
        print(f"代理流设备通用channelId: {channel_id}")
    except Exception as e:
        print(f"测试失败: {str(e)}")
    
    # 测试4: 缺少必要参数
    print("\n4. 测试缺少必要参数的情况")
    try:
        channel_id = client.get_universal_channel_id('gb28181', device_id='34020000001110000001')
        print(f"缺少channel_id参数，返回值: {channel_id}")
    except Exception as e:
        print(f"测试失败: {str(e)}")
    
    # 测试5: 不支持的设备类型
    print("\n5. 测试不支持的设备类型")
    try:
        channel_id = client.get_universal_channel_id('unknown_type', param1='value1')
        print(f"不支持的设备类型，返回值: {channel_id}")
    except Exception as e:
        print(f"测试失败: {str(e)}")
    
    # 测试6: 获取通道播放地址
    print("\n6. 测试获取通道播放地址")
    try:
        # 先获取通用channelId
        channel_id = client.get_universal_channel_id(
            'gb28181',
            device_id='34020000001320000001',
            channel_id='34020000001320000001'
        )
        
        if channel_id:
            # 使用获取到的channelId获取播放地址
            result = client.play_channel(channel_id)
            print(f"获取播放地址结果: {result}")
        else:
            print("无法获取通用channelId，跳过获取播放地址测试")
    except Exception as e:
        print(f"测试失败: {str(e)}")
    
    # 测试7: 直接获取通用通道播放地址
    print("\n7. 测试直接获取通用通道播放地址")
    try:
        result = client.play_universal_channel(
            'gb28181',
            device_id='34020000001320000001',
            channel_id='34020000001310000001'
        )
        print(f"直接获取播放地址结果: {result}")
    except Exception as e:
        print(f"测试失败: {str(e)}")
    
    print("\n测试完成!")

def test_get_channel_list():
    """测试获取通道列表功能"""
    print("\n开始测试获取通道列表功能...")
    
    # 创建WVP客户端实例
    client = WVPClient()
    
    # 测试1: 获取所有通道列表
    print("\n1. 测试获取所有通道列表")
    try:
        result = client.get_channel_list(page=1, count=10)
        total = result.get('total', 0)
        channels = result.get('list', [])
        print(f"获取通道列表结果: 总计{total}个通道，当前页显示{len(channels)}个")
        
        if channels and len(channels) > 0:
            # 打印第一个通道的信息
            print(f"第一个通道信息: {channels[0]}")
    except Exception as e:
        print(f"测试失败: {str(e)}")
        
    # 测试2: 按通道类型获取通道列表
    print("\n2. 测试按通道类型获取通道列表")
    for channel_type, type_name in [(1, "国标设备"), (2, "推流设备"), (3, "拉流代理")]:
        try:
            print(f"\n2.{channel_type+1} 测试获取{type_name}通道列表")
            result = client.get_channel_list(page=1, count=10, channel_type=channel_type)
            total = result.get('total', 0)
            channels = result.get('list', [])
            print(f"获取{type_name}通道列表结果: 总计{total}个通道，当前页显示{len(channels)}个")
            
            if channels and len(channels) > 0:
                # 打印第一个通道的信息
                print(f"第一个{type_name}通道信息: {channels[0]}")
        except Exception as e:
            print(f"测试失败: {str(e)}")
            
    print("\n测试完成!")

if __name__ == '__main__':
    # main()  # 注释掉原来的测试，以免运行时间过长
    test_get_channel_list()  # 只测试获取通道列表功能 