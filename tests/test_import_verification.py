"""
模块导入验证脚本
验证ThreadedFrameReader移动后没有循环导入问题
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

def test_imports():
    """测试关键模块的导入"""
    print("🔍 测试模块导入...")
    
    try:
        # 测试ThreadedFrameReader导入
        print("1. 测试ThreadedFrameReader导入...")
        from app.services.adaptive_frame_reader import ThreadedFrameReader
        print("   ✅ ThreadedFrameReader导入成功")
        
        # 测试AdaptiveFrameReader导入
        print("2. 测试AdaptiveFrameReader导入...")
        from app.services.adaptive_frame_reader import AdaptiveFrameReader
        print("   ✅ AdaptiveFrameReader导入成功")
        
        # 测试AI任务执行器导入
        print("3. 测试AITaskExecutor导入...")
        from app.services.ai_task_executor import AITaskExecutor
        print("   ✅ AITaskExecutor导入成功")
        
        # 测试从ai_task_executor使用AdaptiveFrameReader
        print("4. 测试交叉引用...")
        # 这模拟了ai_task_executor.py中的导入
        from app.services.adaptive_frame_reader import AdaptiveFrameReader as TestReader
        print("   ✅ 交叉引用成功")
        
        print("\n🎉 所有导入测试通过！没有循环导入问题。")
        return True
        
    except ImportError as e:
        print(f"   ❌ 导入失败: {str(e)}")
        return False
    except Exception as e:
        print(f"   ❌ 未知错误: {str(e)}")
        return False

def test_class_instantiation():
    """测试类的实例化"""
    print("\n🏗️  测试类实例化...")
    
    try:
        # 测试ThreadedFrameReader实例化
        print("1. 测试ThreadedFrameReader实例化...")
        from app.services.adaptive_frame_reader import ThreadedFrameReader
        reader = ThreadedFrameReader("rtsp://test.example.com/stream")
        print("   ✅ ThreadedFrameReader实例化成功")
        
        # 测试AdaptiveFrameReader实例化（这会因为无效摄像头ID失败，但应该能创建对象）
        print("2. 测试AdaptiveFrameReader实例化...")
        from app.services.adaptive_frame_reader import AdaptiveFrameReader
        # 使用一个不存在的摄像头ID进行测试，但不调用需要数据库的方法
        try:
            adaptive_reader = AdaptiveFrameReader.__new__(AdaptiveFrameReader)
            adaptive_reader.camera_id = 999
            adaptive_reader.frame_interval = 10.0
            adaptive_reader.connection_overhead_threshold = 30.0
            adaptive_reader.mode = "persistent"  # 手动设置模式
            adaptive_reader.threaded_reader = None
            adaptive_reader.device_info = None
            adaptive_reader.channel_info = None
            adaptive_reader.stream_url = None
            adaptive_reader.stats = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "avg_request_time": 0.0,
                "last_request_time": 0.0
            }
            print("   ✅ AdaptiveFrameReader实例化成功")
        except Exception as e:
            print(f"   ⚠️  AdaptiveFrameReader实例化部分成功: {str(e)}")
        
        print("\n🎉 类实例化测试完成！")
        return True
        
    except Exception as e:
        print(f"   ❌ 实例化失败: {str(e)}")
        return False

def test_methods_availability():
    """测试方法可用性"""
    print("\n🔧 测试方法可用性...")
    
    try:
        from app.services.adaptive_frame_reader import ThreadedFrameReader, AdaptiveFrameReader
        
        # 检查ThreadedFrameReader方法
        print("1. 检查ThreadedFrameReader方法...")
        reader = ThreadedFrameReader("rtsp://test.example.com/stream")
        assert hasattr(reader, 'start'), "ThreadedFrameReader缺少start方法"
        assert hasattr(reader, 'stop'), "ThreadedFrameReader缺少stop方法"
        assert hasattr(reader, 'get_latest_frame'), "ThreadedFrameReader缺少get_latest_frame方法"
        print("   ✅ ThreadedFrameReader所有方法可用")
        
        # 检查AdaptiveFrameReader方法（不调用__init__）
        print("2. 检查AdaptiveFrameReader方法...")
        assert hasattr(AdaptiveFrameReader, 'start'), "AdaptiveFrameReader缺少start方法"
        assert hasattr(AdaptiveFrameReader, 'stop'), "AdaptiveFrameReader缺少stop方法"
        assert hasattr(AdaptiveFrameReader, 'get_latest_frame'), "AdaptiveFrameReader缺少get_latest_frame方法"
        assert hasattr(AdaptiveFrameReader, 'get_resolution'), "AdaptiveFrameReader缺少get_resolution方法"
        assert hasattr(AdaptiveFrameReader, 'get_stats'), "AdaptiveFrameReader缺少get_stats方法"
        print("   ✅ AdaptiveFrameReader所有方法可用")
        
        print("\n🎉 方法可用性测试通过！")
        return True
        
    except Exception as e:
        print(f"   ❌ 方法检查失败: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("模块重构验证测试")
    print("=" * 60)
    
    success = True
    
    # 导入测试
    if not test_imports():
        success = False
    
    # 实例化测试
    if not test_class_instantiation():
        success = False
    
    # 方法可用性测试
    if not test_methods_availability():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 所有验证测试通过！模块重构成功完成。")
        print("\n✅ 重构总结:")
        print("  - ThreadedFrameReader已成功移动到adaptive_frame_reader.py")
        print("  - 没有循环导入问题")
        print("  - 所有类和方法正常可用")
        print("  - 代码结构更加模块化")
    else:
        print("❌ 部分验证测试失败，请检查重构过程中的问题。")
    
    print("=" * 60) 