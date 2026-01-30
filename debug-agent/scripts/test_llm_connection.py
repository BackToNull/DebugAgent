"""
测试 LLM API 连接
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import httpx
from openai import AsyncOpenAI
from config.settings import settings


async def test_connection():
    """测试 LLM API 连接"""
    print("🔍 测试 LLM API 连接...\n")
    
    print(f"API Key: {settings.openai_api_key[:20]}...")
    print(f"Base URL: {settings.openai_base_url}")
    print(f"Model: {settings.llm_model}")
    print()
    
    # 创建自定义 HTTP 客户端，禁用 SSL 验证（解决证书问题）
    http_client = httpx.AsyncClient(verify=False)
    
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=30.0,
        http_client=http_client
    )
    
    print("⚠️  注意: SSL 验证已禁用（仅用于测试）\n")
    
    try:
        print("正在发送请求...")
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "user", "content": "Hello, respond with 'OK' only."}
            ],
            max_tokens=10
        )
        
        print(f"✅ 连接成功!")
        print(f"   响应: {response.choices[0].message.content}")
        
    except Exception as e:
        print(f"❌ 连接失败: {type(e).__name__}")
        print(f"   详情: {str(e)}")
        
        # 打印完整的异常信息
        import traceback
        print(f"\n🔍 详细错误追踪:")
        traceback.print_exc()
        
        # 提供诊断建议
        if "Connection" in str(e) or "connect" in str(e).lower():
            print("\n📋 可能的原因:")
            print("   1. 网络问题 - 检查网络连接")
            print("   2. Base URL 错误 - 检查 OPENAI_BASE_URL 配置")
            print("   3. 代理问题 - 如果有代理，检查代理配置")
        elif "401" in str(e) or "auth" in str(e).lower():
            print("\n📋 可能的原因:")
            print("   1. API Key 无效 - 检查 OPENAI_API_KEY")
            print("   2. API Key 权限不足")
        elif "404" in str(e) or "not found" in str(e).lower():
            print("\n📋 可能的原因:")
            print("   1. 模型名称错误 - 检查 LLM_MODEL 配置")
            print("   2. API 端点错误 - 检查 OPENAI_BASE_URL")


if __name__ == "__main__":
    asyncio.run(test_connection())
