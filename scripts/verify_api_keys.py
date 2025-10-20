#!/usr/bin/env python3
"""
验证 API Keys 脚本
测试所有配置的 API Key 是否可用
"""

import sys
import yaml
import asyncio
import aiohttp
from pathlib import Path
from loguru import logger
from typing import List, Dict

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


def load_api_keys():
    """加载 API Keys 配置"""
    config_path = ROOT_DIR / "config" / "api_keys.yaml"
    
    if not config_path.exists():
        logger.error(f"API Keys 配置文件不存在: {config_path}")
        sys.exit(1)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config['api_keys']


async def test_api_key(key_config: Dict, session: aiohttp.ClientSession) -> Dict:
    """测试单个 API Key"""
    key = key_config['key']
    key_id = key_config['key_id']
    
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    
    # 简单的测试请求
    payload = {
        "model": "qwen-vl-plus",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "测试"}
                ]
            }
        ],
        "max_tokens": 10
    }
    
    try:
        async with session.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status == 200:
                result = await response.json()
                return {
                    'key_id': key_id,
                    'status': 'success',
                    'message': '可用',
                    'response_time': response.headers.get('X-Response-Time', 'N/A')
                }
            else:
                error_text = await response.text()
                return {
                    'key_id': key_id,
                    'status': 'error',
                    'message': f"HTTP {response.status}: {error_text[:100]}"
                }
    except asyncio.TimeoutError:
        return {
            'key_id': key_id,
            'status': 'error',
            'message': '请求超时'
        }
    except Exception as e:
        return {
            'key_id': key_id,
            'status': 'error',
            'message': str(e)
        }


async def test_all_keys(api_keys: List[Dict]):
    """并发测试所有 API Keys"""
    async with aiohttp.ClientSession() as session:
        tasks = [test_api_key(key_config, session) for key_config in api_keys if key_config.get('enabled', True)]
        results = await asyncio.gather(*tasks)
        return results


def print_results(results: List[Dict]):
    """打印测试结果"""
    logger.info("\n=== API Keys 验证结果 ===\n")
    
    success_count = 0
    error_count = 0
    
    for result in results:
        key_id = result['key_id']
        status = result['status']
        message = result['message']
        
        if status == 'success':
            logger.success(f"✅ {key_id}: {message}")
            success_count += 1
        else:
            logger.error(f"❌ {key_id}: {message}")
            error_count += 1
    
    logger.info(f"\n总计: {len(results)} 个 Key")
    logger.info(f"成功: {success_count} 个")
    logger.info(f"失败: {error_count} 个")
    
    if error_count > 0:
        logger.warning(f"\n⚠️  有 {error_count} 个 API Key 不可用，请检查配置")
        return False
    else:
        logger.success("\n✅ 所有 API Key 均可用")
        return True


def main():
    logger.info("=== 开始验证 API Keys ===")
    
    # 加载配置
    api_keys = load_api_keys()
    
    if not api_keys:
        logger.error("未找到任何 API Key 配置")
        sys.exit(1)
    
    # 测试所有 Keys
    results = asyncio.run(test_all_keys(api_keys))
    
    # 打印结果
    success = print_results(results)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
