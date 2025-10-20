#!/usr/bin/env python3
"""修复 loguru 日志格式：%s -> {}"""

import re
from pathlib import Path

def fix_logger_format(file_path: Path) -> bool:
    """修复单个文件的日志格式"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 匹配 logger.xxx("... %s ...", arg1, arg2, ...)
    # 将 %s 替换为 {}
    pattern = r'(logger\.(info|warning|error|debug)\(["\'])([^"\']*?)(%s)([^"\']*?)(["\'])((?:,\s*[^)]+)?)\)'
    
    def replace_func(match):
        prefix = match.group(1)  # logger.info("
        log_level = match.group(2)  # info
        before = match.group(3)  # text before %s
        percent_s = match.group(4)  # %s
        after = match.group(5)  # text after %s
        quote = match.group(6)  # "
        args = match.group(7)  # , arg1, arg2
        
        # 替换 %s 为 {}
        new_message = before + '{}' + after
        
        return f'{prefix}{new_message}{quote}{args})'
    
    # 多次替换以处理多个 %s
    for _ in range(10):  # 最多 10 个占位符
        new_content = re.sub(pattern, replace_func, content)
        if new_content == content:
            break
        content = new_content
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        print(f"✅ Fixed: {file_path}")
        return True
    return False

def main():
    """修复所有文件"""
    base_dir = Path(__file__).parent.parent
    algo_dir = base_dir / 'algo'
    
    files_to_fix = [
        algo_dir / 'rtsp_detect' / 'pipeline.py',
        algo_dir / 'rtsp_detect' / 'video_stream.py',
        algo_dir / 'rtsp_detect' / 'session_manager.py',
        algo_dir / 'rtsp_detect' / 'yolo_detector.py',
    ]
    
    fixed_count = 0
    for file_path in files_to_fix:
        if file_path.exists():
            if fix_logger_format(file_path):
                fixed_count += 1
        else:
            print(f"⚠️ Not found: {file_path}")
    
    print(f"\n🎉 Fixed {fixed_count} files")

if __name__ == '__main__':
    main()
