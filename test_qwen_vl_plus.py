# test_qwen_vl_plus.py
import os
import sys
import base64
from pathlib import Path

from openai import OpenAI

BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-vl-plus"

def encode_as_data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python test_qwen_vl_plus.py <图片路径>")
        sys.exit(1)

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print("找不到图片:", image_path)
        sys.exit(1)

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("环境变量 DASHSCOPE_API_KEY 未设置")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    data_url = encode_as_data_url(image_path)

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": [{"type": "text", "text": "You are a helpful assistant."}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                    {
                        "type": "text",
                        "text": "请描述图像中的交通场景，并判断是否存在危险驾驶。",
                    },
                ],
            },
        ],
    )

    if resp.choices:
        print("模型回复：\n", resp.choices[0].message.content)
    else:
        print("未收到模型输出，原始响应：", resp)

if __name__ == "__main__":
    main()
