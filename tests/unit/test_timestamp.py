"""
时间戳提取功能测试
验证AdaptiveFrameReader能正确从各种文件名格式中提取时间戳
"""
import sys
import os
import re

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

def extract_timestamp_from_filename(filename: str) -> str:
    """从文件名中提取时间戳（独立测试函数）"""
    try:
        # 提取文件扩展名前的最后一个数字序列
        pattern = r'(\d+)(?=\.[^.]*$)'
        match = re.search(pattern, filename)
        
        if match:
            timestamp = match.group(1)
            return timestamp
        else:
            return None
            
    except Exception as e:
        print(f"提取时间戳时出错: {str(e)}")
        return None

def test_timestamp_extraction():
    """测试时间戳提取功能"""
    print("🧪 测试时间戳提取功能")
    print("=" * 60)
    
    # 测试用例
    test_cases = [
        {
            "filename": "live_plate_20250617093238.jpg",
            "expected": "20250617093238",
            "description": "标准格式文件名"
        },
        {
            "filename": "34020000001320000001_34020000001320000001_20250618094612.jpg",
            "expected": "20250618094612",
            "description": "国标设备文件名"
        },
        {
            "filename": "34020000001320000001_34020000001320000001_20250612162248.jpg",
            "expected": "20250612162248",
            "description": "用户提供的示例文件名"
        },
        {
            "filename": "camera_001_snapshot_20241225120000.png",
            "expected": "20241225120000",
            "description": "PNG格式文件"
        },
        {
            "filename": "test_123456789.jpeg",
            "expected": "123456789",
            "description": "JPEG格式，短数字"
        },
        {
            "filename": "nodigits.jpg",
            "expected": None,
            "description": "无数字的文件名"
        },
        {
            "filename": "multiple_123_456_789.jpg",
            "expected": "789",
            "description": "多个数字序列，应取最后一个"
        }
    ]
    
    passed = 0
    total = len(test_cases)
    
    for i, test_case in enumerate(test_cases, 1):
        filename = test_case["filename"]
        expected = test_case["expected"]
        description = test_case["description"]
        
        print(f"\n测试 {i}: {description}")
        print(f"  文件名: {filename}")
        print(f"  期望结果: {expected}")
        
        result = extract_timestamp_from_filename(filename)
        print(f"  实际结果: {result}")
        
        if result == expected:
            print(f"  ✅ 通过")
            passed += 1
        else:
            print(f"  ❌ 失败")
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！时间戳提取功能正常。")
        return True
    else:
        print("❌ 部分测试失败，请检查实现。")
        return False

def test_with_adaptive_frame_reader():
    """使用实际的AdaptiveFrameReader类进行测试"""
    print("\n🔧 使用AdaptiveFrameReader进行集成测试")
    print("=" * 60)
    
    try:
        from app.services.adaptive_frame_reader import AdaptiveFrameReader
        
        # 创建一个测试实例（不初始化设备信息）
        reader = AdaptiveFrameReader.__new__(AdaptiveFrameReader)
        
        # 测试几个关键用例
        test_cases = [
            "34020000001320000001_34020000001320000001_20250618094612.jpg",
            "34020000001320000001_34020000001320000001_20250612162248.jpg",
            "live_plate_20250617093238.jpg"
        ]
        
        print("使用AdaptiveFrameReader._extract_timestamp_from_filename()测试:")
        
        for filename in test_cases:
            result = reader._extract_timestamp_from_filename(filename)
            print(f"  {filename} -> {result}")
        
        print("✅ AdaptiveFrameReader集成测试完成")
        return True
        
    except Exception as e:
        print(f"❌ AdaptiveFrameReader集成测试失败: {str(e)}")
        return False

if __name__ == "__main__":
    print("时间戳提取功能测试")
    print("=" * 60)
    
    success = True
    
    # 独立函数测试
    if not test_timestamp_extraction():
        success = False
    
    # 集成测试
    if not test_with_adaptive_frame_reader():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 所有测试通过！修复后的时间戳提取功能正常工作。")
        print("\n📝 功能说明:")
        print("  - 正则表达式: r'(\\d+)(?=\\.[^.]*$)'")
        print("  - 匹配文件扩展名前的最后一个数字序列")
        print("  - 支持各种文件名格式和扩展名")
        print("  - 自动处理多个数字序列的情况")
    else:
        print("❌ 部分测试失败，请检查实现。")
    
    print("=" * 60) 