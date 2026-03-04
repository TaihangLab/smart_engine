"""
AdaptiveFrameReader 测试脚本
"""
import sys
import os
import time
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app.services.adaptive_frame_reader import AdaptiveFrameReader

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_adaptive_frame_reader():
    """测试自适应帧读取器"""
    
    # 测试摄像头ID（请根据实际情况修改）
    camera_id = 16
    
    print("=" * 60)
    print("AdaptiveFrameReader 功能测试")
    print("=" * 60)
    
    # 测试1：高频模式（持续连接）
    print("\n🔄 测试1: 高频模式（间隔5秒，应使用持续连接）")
    try:
        reader1 = AdaptiveFrameReader(
            camera_id=camera_id,
            frame_interval=5.0,
            connection_overhead_threshold=30.0
        )
        
        print(f"  模式: {reader1.mode}")
        print(f"  连接开销阈值: {reader1.connection_overhead_threshold}秒")
        
        if reader1.start():
            print("  ✅ 启动成功")
            
            # 获取几帧测试
            for i in range(3):
                print(f"  获取第{i+1}帧...")
                frame = reader1.get_latest_frame()
                if frame is not None:
                    print(f"    ✅ 成功获取帧，尺寸: {frame.shape}")
                else:
                    print("    ❌ 获取帧失败")
                time.sleep(2)
            
            # 显示统计信息
            stats = reader1.get_stats()
            print(f"  统计信息: {stats['stats']}")
            
            reader1.stop()
            print("  ✅ 停止成功")
        else:
            print("  ❌ 启动失败")
            
    except Exception as e:
        print(f"  ❌ 测试1失败: {str(e)}")
    
    print("\n" + "="*60)
    
    # 测试2：低频模式（按需截图）
    print("\n📸 测试2: 低频模式（间隔60秒，应使用按需截图）")
    try:
        reader2 = AdaptiveFrameReader(
            camera_id=camera_id,
            frame_interval=60.0,
            connection_overhead_threshold=30.0
        )
        
        print(f"  模式: {reader2.mode}")
        print(f"  连接开销阈值: {reader2.connection_overhead_threshold}秒")
        
        if reader2.start():
            print("  ✅ 启动成功")
            
            # 获取几帧测试
            for i in range(2):
                print(f"  获取第{i+1}帧（按需截图）...")
                start_time = time.time()
                frame = reader2.get_latest_frame()
                request_time = time.time() - start_time
                
                if frame is not None:
                    print(f"    ✅ 成功获取帧，尺寸: {frame.shape}，耗时: {request_time:.2f}秒")
                else:
                    print(f"    ❌ 获取帧失败，耗时: {request_time:.2f}秒")
                
                if i < 1:  # 避免最后一次等待
                    print("    等待5秒后继续...")
                    time.sleep(5)
            
            # 显示统计信息
            stats = reader2.get_stats()
            print(f"  统计信息: {stats['stats']}")
            
            reader2.stop()
            print("  ✅ 停止成功")
        else:
            print("  ❌ 启动失败")
            
    except Exception as e:
        print(f"  ❌ 测试2失败: {str(e)}")
    
    print("\n" + "="*60)
    
    # 测试3：分辨率获取
    print("\n📐 测试3: 分辨率获取测试")
    try:
        reader3 = AdaptiveFrameReader(
            camera_id=camera_id,
            frame_interval=10.0,
            connection_overhead_threshold=30.0
        )
        
        if reader3.start():
            width, height = reader3.get_resolution()
            print(f"  ✅ 分辨率: {width}x{height}")
            reader3.stop()
        else:
            print("  ❌ 启动失败")
            
    except Exception as e:
        print(f"  ❌ 测试3失败: {str(e)}")
    
    print("\n" + "="*60)
    print("测试完成！")

def benchmark_modes():
    """性能基准测试"""
    
    camera_id = 16
    test_frames = 5
    
    print("\n🚀 性能基准测试")
    print("=" * 60)
    
    # 测试持续连接模式性能
    print("\n⚡ 持续连接模式性能测试")
    try:
        reader_persistent = AdaptiveFrameReader(
            camera_id=camera_id,
            frame_interval=1.0,  # 强制使用持续连接
            connection_overhead_threshold=30.0
        )
        
        if reader_persistent.start():
            start_time = time.time()
            success_count = 0
            
            for i in range(test_frames):
                frame = reader_persistent.get_latest_frame()
                if frame is not None:
                    success_count += 1
                time.sleep(0.5)
            
            total_time = time.time() - start_time
            avg_time = total_time / test_frames
            
            print(f"  总时间: {total_time:.2f}秒")
            print(f"  平均每帧: {avg_time:.2f}秒")
            print(f"  成功率: {success_count}/{test_frames}")
            
            reader_persistent.stop()
        else:
            print("  ❌ 启动失败")
            
    except Exception as e:
        print(f"  ❌ 持续连接测试失败: {str(e)}")
    
    # 测试按需截图模式性能
    print("\n📷 按需截图模式性能测试")
    try:
        reader_demand = AdaptiveFrameReader(
            camera_id=camera_id,
            frame_interval=100.0,  # 强制使用按需模式
            connection_overhead_threshold=30.0
        )
        
        if reader_demand.start():
            start_time = time.time()
            success_count = 0
            
            for i in range(3):  # 按需模式测试较少帧数
                frame_start = time.time()
                frame = reader_demand.get_latest_frame()
                frame_time = time.time() - frame_start
                
                if frame is not None:
                    success_count += 1
                    print(f"  第{i+1}帧: {frame_time:.2f}秒")
                else:
                    print(f"  第{i+1}帧: 失败 ({frame_time:.2f}秒)")
                
                if i < 2:
                    time.sleep(1)
            
            total_time = time.time() - start_time
            avg_time = total_time / 3
            
            print(f"  总时间: {total_time:.2f}秒")
            print(f"  平均每帧: {avg_time:.2f}秒")
            print(f"  成功率: {success_count}/3")
            
            reader_demand.stop()
        else:
            print("  ❌ 启动失败")
            
    except Exception as e:
        print(f"  ❌ 按需截图测试失败: {str(e)}")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    print("AdaptiveFrameReader 测试工具")
    print("请确保：")
    print("1. WVP服务器正在运行")
    print("2. 摄像头ID存在且在线")
    print("3. 网络连接正常")
    
    input("\n按回车键开始测试...")
    
    # 基本功能测试
    test_adaptive_frame_reader()
    
    # 性能基准测试
    choice = input("\n是否进行性能基准测试？(y/n): ")
    if choice.lower() == 'y':
        benchmark_modes()
    
    print("\n✅ 所有测试完成！") 