# -*- coding: utf-8 -*-
"""
图像生成器

使用多模态 AI 生成市场分析图表/海报
"""

import asyncio
import base64
import logging
import httpx
import io
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GeneratedImage:
    """生成的图像"""
    data: bytes  # 图像二进制数据
    format: str  # "png", "jpeg"
    prompt: str  # 生成提示词
    timestamp: datetime
    model: str
    
    def to_base64(self) -> str:
        return base64.b64encode(self.data).decode('utf-8')
    
    def save(self, path: str):
        Path(path).write_bytes(self.data)


class ImageGenerator:
    """
    图像生成器
    
    支持多种图像生成模式：
    1. DALL-E 3（OpenAI）
    2. GPT-4o 图像生成
    3. 其他兼容的图像生成 API
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "dall-e-3",
        timeout: int = 120
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
        return self._client
    
    async def close(self):
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def generate_market_poster(
        self,
        report_content: str,
        style: str = "modern",
        size: str = "1024x1024"
    ) -> Tuple[Optional[GeneratedImage], Optional[str]]:
        """
        生成市场分析海报
        
        Args:
            report_content: 市场报告内容
            style: 风格 (modern, professional, minimalist, vibrant)
            size: 图像尺寸 (1024x1024, 1024x1792, 1792x1024)
        
        Returns:
            (GeneratedImage, error_message)
        """
        prompt = self._build_poster_prompt(report_content, style)
        return await self.generate_image(prompt, size)
    
    def _build_poster_prompt(self, report_content: str, style: str) -> str:
        """构建海报生成提示词"""
        # 提取关键信息
        key_info = self._extract_key_info(report_content)
        
        style_prompts = {
            "modern": "modern, clean design with gradient backgrounds, minimalist icons",
            "professional": "professional business style, dark theme, elegant typography",
            "minimalist": "minimalist design, white background, simple geometric shapes",
            "vibrant": "vibrant colors, dynamic composition, eye-catching graphics"
        }
        
        style_desc = style_prompts.get(style, style_prompts["modern"])
        
        prompt = f"""Create a cryptocurrency market analysis infographic poster with the following elements:

Market Overview:
{key_info}

Design Style: {style_desc}

Requirements:
- Include cryptocurrency icons (BTC, ETH, SOL)
- Show market trend indicators (up/down arrows)
- Use appropriate color coding (green for gains, red for losses)
- Include data visualization elements (charts, graphs)
- Professional financial design aesthetic
- Chinese text support for title "加密货币市场分析"
- Include today's date
- Clean, readable layout

The poster should look like a professional market report infographic that could be shared on social media or financial news platforms."""
        
        return prompt
    
    def _extract_key_info(self, content: str) -> str:
        """从报告内容提取关键信息"""
        # 限制长度，提取核心数据
        lines = content.split('\n')
        key_lines = []
        
        keywords = ['BTC', 'ETH', 'SOL', '涨', '跌', '%', '价格', '市场', '趋势']
        
        for line in lines:
            if any(kw in line for kw in keywords):
                key_lines.append(line.strip())
            if len(key_lines) >= 10:
                break
        
        return '\n'.join(key_lines) if key_lines else content[:500]
    
    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard"
    ) -> Tuple[Optional[GeneratedImage], Optional[str]]:
        """
        生成图像
        
        Args:
            prompt: 生成提示词
            size: 图像尺寸
            quality: 质量 (standard, hd)
        
        Returns:
            (GeneratedImage, error_message)
        """
        try:
            client = await self._get_client()
            
            # 根据模型选择不同的 API
            if self.model.startswith("dall-e"):
                return await self._generate_dalle(client, prompt, size, quality)
            elif "gpt-4" in self.model.lower():
                return await self._generate_gpt4o(client, prompt, size)
            else:
                return await self._generate_compatible(client, prompt, size)
                
        except httpx.TimeoutException:
            error = "图像生成超时，请稍后重试"
            logger.error(error)
            return None, error
        except Exception as e:
            error = f"图像生成失败: {str(e)}"
            logger.error(error, exc_info=True)
            return None, error
    
    async def _generate_dalle(
        self,
        client: httpx.AsyncClient,
        prompt: str,
        size: str,
        quality: str
    ) -> Tuple[Optional[GeneratedImage], Optional[str]]:
        """使用 DALL-E API 生成图像"""
        url = f"{self.base_url}/images/generations"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": quality,
            "response_format": "b64_json"
        }
        
        response = await client.post(url, json=payload)
        
        if response.status_code != 200:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", str(response.status_code))
            return None, f"DALL-E API 错误: {error_msg}"
        
        data = response.json()
        image_data = base64.b64decode(data["data"][0]["b64_json"])
        
        return GeneratedImage(
            data=image_data,
            format="png",
            prompt=prompt,
            timestamp=datetime.now(),
            model=self.model
        ), None
    
    async def _generate_gpt4o(
        self,
        client: httpx.AsyncClient,
        prompt: str,
        size: str
    ) -> Tuple[Optional[GeneratedImage], Optional[str]]:
        """使用 GPT-4o 生成图像"""
        url = f"{self.base_url}/chat/completions"
        
        # GPT-4o 图像生成使用特殊格式
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Generate an image: {prompt}"
                        }
                    ]
                }
            ],
            "max_tokens": 4096
        }
        
        response = await client.post(url, json=payload)
        
        if response.status_code != 200:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", str(response.status_code))
            return None, f"GPT-4o API 错误: {error_msg}"
        
        data = response.json()
        
        # 检查响应中是否包含图像
        message = data.get("choices", [{}])[0].get("message", {})
        content = message.get("content", [])
        
        for item in content if isinstance(content, list) else []:
            if isinstance(item, dict) and item.get("type") == "image":
                image_data = base64.b64decode(item.get("image", {}).get("data", ""))
                return GeneratedImage(
                    data=image_data,
                    format="png",
                    prompt=prompt,
                    timestamp=datetime.now(),
                    model=self.model
                ), None
        
        return None, "GPT-4o 未返回图像"
    
    async def _generate_compatible(
        self,
        client: httpx.AsyncClient,
        prompt: str,
        size: str
    ) -> Tuple[Optional[GeneratedImage], Optional[str]]:
        """使用兼容 API 生成图像"""
        # 尝试使用标准 OpenAI 图像生成 API
        url = f"{self.base_url}/images/generations"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json"
        }
        
        response = await client.post(url, json=payload)
        
        if response.status_code != 200:
            # 回退到描述文本
            return None, f"图像生成 API 不可用 (HTTP {response.status_code})"
        
        data = response.json()
        
        if "data" in data and len(data["data"]) > 0:
            image_b64 = data["data"][0].get("b64_json")
            if image_b64:
                image_data = base64.b64decode(image_b64)
                return GeneratedImage(
                    data=image_data,
                    format="png",
                    prompt=prompt,
                    timestamp=datetime.now(),
                    model=self.model
                ), None
        
        return None, "API 未返回有效图像数据"
    
    async def generate_chart_description(
        self,
        report_content: str
    ) -> str:
        """
        生成图表描述（当无法生成实际图像时的备选方案）
        
        返回详细的文字描述，用户可以据此理解市场情况
        """
        try:
            client = await self._get_client()
            url = f"{self.base_url}/chat/completions"
            
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个数据可视化专家。请根据市场报告内容，用文字描述一个理想的市场分析图表应该包含哪些元素，以及各个数据点的视觉呈现方式。"
                    },
                    {
                        "role": "user",
                        "content": f"请根据以下市场报告，描述一个专业的加密货币市场分析图表应该如何呈现：\n\n{report_content[:2000]}"
                    }
                ],
                "max_tokens": 1000
            }
            
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                return "无法生成图表描述"
                
        except Exception as e:
            logger.error(f"生成图表描述失败: {e}")
            return f"生成图表描述时出错: {str(e)}"


class ImageGeneratorFactory:
    """图像生成器工厂"""
    
    @staticmethod
    def create(
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "dall-e-3"
    ) -> ImageGenerator:
        """创建图像生成器实例"""
        return ImageGenerator(
            api_key=api_key,
            base_url=base_url,
            model=model
        )
    
    @staticmethod
    def create_from_config(config: Dict[str, Any]) -> Optional[ImageGenerator]:
        """从配置创建图像生成器"""
        api_key = config.get("OPENAI_API_KEY") or config.get("api_key")
        if not api_key:
            logger.warning("未配置 API Key，图像生成功能不可用")
            return None
        
        return ImageGenerator(
            api_key=api_key,
            base_url=config.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=config.get("IMAGE_MODEL", "dall-e-3")
        )


# 全局实例
_image_generator: Optional[ImageGenerator] = None


def get_image_generator() -> Optional[ImageGenerator]:
    """获取全局图像生成器"""
    return _image_generator


def init_image_generator(
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "dall-e-3"
) -> ImageGenerator:
    """初始化全局图像生成器"""
    global _image_generator
    _image_generator = ImageGenerator(
        api_key=api_key,
        base_url=base_url,
        model=model
    )
    return _image_generator
