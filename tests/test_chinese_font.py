"""
中文字体加载测试脚本
验证车牌识别技能的中文字体加载和显示功能
"""
import sys
import os
import cv2
import numpy as np

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

def test_font_loading():
    """测试字体加载功能"""
    print("🔤 测试中文字体加载功能")
    print("=" * 60)
    
    try:
        from app.plugins.skills.carplate_detector_skill import PlateRecognitionSkill
        
        # 创建技能实例
        config = PlateRecognitionSkill.DEFAULT_CONFIG.copy()
        skill = PlateRecognitionSkill(config)
        
        # 检查字体加载结果
        print(f"字体加载状态:")
        print(f"  - 主字体加载: {'✅ 成功' if skill.font_main is not None else '❌ 失败'}")
        print(f"  - 副字体加载: {'✅ 成功' if skill.font_sub is not None else '❌ 失败'}")
        print(f"  - 中文显示模式: {'✅ 启用' if skill.use_chinese_display else '❌ 禁用（将使用英文）'}")
        
        if skill.use_chinese_display:
            print("  - 字体加载成功，将显示中文界面")
        else:
            print("  - 字体加载失败或未找到，将使用英文界面")
        
        return skill.use_chinese_display
        
    except Exception as e:
        print(f"❌ 字体加载测试失败: {str(e)}")
        return False

def test_text_rendering():
    """测试文字绘制功能"""
    print("\n🖼️  测试文字绘制功能")
    print("=" * 60)
    
    try:
        from app.plugins.skills.carplate_detector_skill import PlateRecognitionSkill
        
        # 创建技能实例
        config = PlateRecognitionSkill.DEFAULT_CONFIG.copy()
        skill = PlateRecognitionSkill(config)
        
        # 创建测试图像
        test_frame = np.zeros((600, 800, 3), dtype=np.uint8)
        test_frame[:] = (50, 50, 50)  # 深灰色背景
        
        # 模拟检测结果
        test_detections = [
            {
                "bbox": [100, 100, 300, 150],
                "confidence": 0.95,
                "plate_text": "川A12345",
                "plate_score": 0.88,
                "class_name": "plate"
            },
            {
                "bbox": [400, 200, 600, 250],
                "confidence": 0.87,
                "plate_text": "京B67890",
                "plate_score": 0.92,
                "class_name": "plate"
            }
        ]
        
        # 使用技能的绘制方法
        try:
            annotated_frame = skill.draw_detections_on_frame(test_frame, test_detections)
            
            # 保存测试结果图像
            output_path = "test_chinese_font_output.jpg"
            cv2.imwrite(output_path, annotated_frame)
            
            print(f"✅ 文字绘制测试成功")
            print(f"  - 字体模式: {'中文' if skill.use_chinese_display else '英文'}")
            print(f"  - 测试图像已保存: {output_path}")
            print(f"  - 图像尺寸: {annotated_frame.shape}")
            
            # 显示预期的文字内容
            if skill.use_chinese_display:
                print(f"  - 预期显示内容: '车牌: 川A12345', '检测:0.95 识别:0.88'")
            else:
                print(f"  - 预期显示内容: 'Plate: 川A12345', 'Det:0.95 Rec:0.88'")
            
            return True
            
        except Exception as render_error:
            print(f"❌ 文字绘制失败: {str(render_error)}")
            return False
        
    except Exception as e:
        print(f"❌ 文字绘制测试失败: {str(e)}")
        return False

def test_font_paths():
    """测试系统字体路径"""
    print("\n📁 检查系统字体路径")
    print("=" * 60)
    
    font_paths = [
        # Linux系统字体 - 中文字体
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/arphic/ukai.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/chinese/TrueType/wqy-zenhei.ttc",
        "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
        
        # Windows系统字体
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    
    found_fonts = []
    missing_fonts = []
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            found_fonts.append(font_path)
            print(f"  ✅ {font_path}")
        else:
            missing_fonts.append(font_path)
            print(f"  ❌ {font_path}")
    
    print(f"\n📊 字体路径统计:")
    print(f"  - 找到字体: {len(found_fonts)} 个")
    print(f"  - 缺失字体: {len(missing_fonts)} 个")
    
    if found_fonts:
        print(f"\n🎯 推荐安装以下中文字体包:")
        print(f"  - Ubuntu/Debian: sudo apt-get install fonts-wqy-microhei fonts-wqy-zenhei fonts-noto-cjk")
        print(f"  - CentOS/RHEL: sudo yum install wqy-microhei-fonts wqy-zenhei-fonts google-noto-cjk-fonts")
        print(f"  - 刷新字体缓存: sudo fc-cache -fv")
    
    return len(found_fonts) > 0

if __name__ == "__main__":
    print("中文字体加载和显示测试")
    print("=" * 60)
    
    success_count = 0
    total_tests = 3
    
    # 字体路径检查
    if test_font_paths():
        success_count += 1
    
    # 字体加载测试
    if test_font_loading():
        success_count += 1
    
    # 文字绘制测试
    if test_text_rendering():
        success_count += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {success_count}/{total_tests} 通过")
    
    if success_count == total_tests:
        print("🎉 所有测试通过！中文字体功能正常。")
    elif success_count > 0:
        print("⚠️  部分测试通过，可能需要安装更多中文字体。")
        print("\n💡 如果Linux系统中文不显示，请安装中文字体：")
        print("   sudo apt-get install fonts-wqy-microhei fonts-wqy-zenhei")
        print("   sudo fc-cache -fv")
    else:
        print("❌ 所有测试失败，请检查字体安装和代码实现。")
    
    print("=" * 60) 