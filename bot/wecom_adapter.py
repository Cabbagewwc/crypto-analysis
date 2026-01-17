# -*- coding: utf-8 -*-
"""
企业微信应用适配器

支持企业微信应用的双向消息交互
"""

import asyncio
import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
import base64
import struct
import socket

import httpx
from Crypto.Cipher import AES

from bot.context_manager import ContextManager, get_context_manager
from bot.message_handler import (
    MessageHandler,
    UserMessage,
    BotResponse,
    get_message_handler
)
from bot.image_generator import get_image_generator

logger = logging.getLogger(__name__)


@dataclass
class WeComConfig:
    """企业微信应用配置"""
    corp_id: str  # 企业 ID
    agent_id: int  # 应用 AgentId
    secret: str  # 应用 Secret
    token: str  # 回调 Token
    encoding_aes_key: str  # 回调 EncodingAESKey
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> Optional["WeComConfig"]:
        """从字典创建配置"""
        corp_id = config.get("WECOM_CORP_ID")
        agent_id = config.get("WECOM_AGENT_ID")
        secret = config.get("WECOM_SECRET")
        token = config.get("WECOM_TOKEN")
        encoding_aes_key = config.get("WECOM_ENCODING_AES_KEY")
        
        if not all([corp_id, agent_id, secret, token, encoding_aes_key]):
            return None
        
        return cls(
            corp_id=corp_id,
            agent_id=int(agent_id),
            secret=secret,
            token=token,
            encoding_aes_key=encoding_aes_key
        )


class WXBizMsgCrypt:
    """
    企业微信消息加解密
    
    参考官方 SDK 实现
    """
    
    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        self.token = token
        self.corp_id = corp_id
        self.aes_key = base64.b64decode(encoding_aes_key + "=")
    
    def _get_random_str(self) -> str:
        """生成随机字符串"""
        import random
        import string
        return "".join(random.choices(string.ascii_letters + string.digits, k=16))
    
    def _pkcs7_encode(self, text: bytes) -> bytes:
        """PKCS7 填充"""
        block_size = 32
        text_length = len(text)
        amount_to_pad = block_size - (text_length % block_size)
        if amount_to_pad == 0:
            amount_to_pad = block_size
        pad = bytes([amount_to_pad]) * amount_to_pad
        return text + pad
    
    def _pkcs7_decode(self, decrypted: bytes) -> bytes:
        """PKCS7 去填充"""
        pad = decrypted[-1]
        return decrypted[:-pad]
    
    def encrypt(self, reply_msg: str, nonce: str, timestamp: str = None) -> Tuple[str, str]:
        """
        加密消息
        
        返回 (加密后的 XML, 签名)
        """
        if timestamp is None:
            timestamp = str(int(time.time()))
        
        # 构建明文
        random_str = self._get_random_str()
        msg_bytes = reply_msg.encode("utf-8")
        msg_len = struct.pack(">I", len(msg_bytes))
        
        text = random_str.encode() + msg_len + msg_bytes + self.corp_id.encode()
        text = self._pkcs7_encode(text)
        
        # AES 加密
        iv = self.aes_key[:16]
        cipher = AES.new(self.aes_key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(text)
        encrypt_msg = base64.b64encode(encrypted).decode()
        
        # 计算签名
        signature = self._create_signature(self.token, timestamp, nonce, encrypt_msg)
        
        # 构建响应 XML
        resp_xml = f"""<xml>
<Encrypt><![CDATA[{encrypt_msg}]]></Encrypt>
<MsgSignature><![CDATA[{signature}]]></MsgSignature>
<TimeStamp>{timestamp}</TimeStamp>
<Nonce><![CDATA[{nonce}]]></Nonce>
</xml>"""
        
        return resp_xml, signature
    
    def decrypt(self, msg_signature: str, timestamp: str, nonce: str, encrypt_msg: str) -> str:
        """解密消息"""
        # 验证签名
        signature = self._create_signature(self.token, timestamp, nonce, encrypt_msg)
        if signature != msg_signature:
            raise ValueError("签名验证失败")
        
        # AES 解密
        iv = self.aes_key[:16]
        cipher = AES.new(self.aes_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(base64.b64decode(encrypt_msg))
        decrypted = self._pkcs7_decode(decrypted)
        
        # 解析明文
        # 前 16 字节是随机字符串
        # 接下来 4 字节是消息长度
        # 然后是消息内容
        # 最后是 corp_id
        msg_len = struct.unpack(">I", decrypted[16:20])[0]
        msg = decrypted[20:20+msg_len].decode("utf-8")
        
        return msg
    
    def _create_signature(self, token: str, timestamp: str, nonce: str, encrypt_msg: str) -> str:
        """创建签名"""
        sort_list = [token, timestamp, nonce, encrypt_msg]
        sort_list.sort()
        sha = hashlib.sha1("".join(sort_list).encode())
        return sha.hexdigest()
    
    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """验证 URL（用于配置回调地址）"""
        return self.decrypt(msg_signature, timestamp, nonce, echostr)


class WeComAdapter:
    """
    企业微信应用适配器
    
    功能：
    1. 接收用户消息（通过回调）
    2. 发送消息给用户
    3. 与 AI 进行对话
    """
    
    API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"
    
    def __init__(
        self,
        config: WeComConfig,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        context_manager: Optional[ContextManager] = None,
        message_handler: Optional[MessageHandler] = None
    ):
        self.config = config
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        
        self.context_manager = context_manager or get_context_manager()
        self.message_handler = message_handler or get_message_handler()
        
        self.crypt = WXBizMsgCrypt(
            token=config.token,
            encoding_aes_key=config.encoding_aes_key,
            corp_id=config.corp_id
        )
        
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client
    
    async def close(self):
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _get_access_token(self) -> str:
        """获取 Access Token"""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        
        client = await self._get_client()
        url = f"{self.API_BASE}/gettoken"
        params = {
            "corpid": self.config.corp_id,
            "corpsecret": self.config.secret
        }
        
        response = await client.get(url, params=params)
        data = response.json()
        
        if data.get("errcode") != 0:
            raise ValueError(f"获取 Access Token 失败: {data.get('errmsg')}")
        
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 7200) - 60
        
        return self._access_token
    
    async def send_text_message(self, user_id: str, content: str):
        """发送文本消息"""
        access_token = await self._get_access_token()
        client = await self._get_client()
        
        url = f"{self.API_BASE}/message/send?access_token={access_token}"
        payload = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": self.config.agent_id,
            "text": {
                "content": content
            }
        }
        
        response = await client.post(url, json=payload)
        data = response.json()
        
        if data.get("errcode") != 0:
            logger.error(f"发送消息失败: {data.get('errmsg')}")
            return False
        
        return True
    
    async def send_image_message(self, user_id: str, image_data: bytes):
        """发送图片消息"""
        # 先上传图片获取 media_id
        media_id = await self._upload_media(image_data, "image")
        if not media_id:
            return False
        
        access_token = await self._get_access_token()
        client = await self._get_client()
        
        url = f"{self.API_BASE}/message/send?access_token={access_token}"
        payload = {
            "touser": user_id,
            "msgtype": "image",
            "agentid": self.config.agent_id,
            "image": {
                "media_id": media_id
            }
        }
        
        response = await client.post(url, json=payload)
        data = response.json()
        
        if data.get("errcode") != 0:
            logger.error(f"发送图片失败: {data.get('errmsg')}")
            return False
        
        return True
    
    async def _upload_media(self, data: bytes, media_type: str = "image") -> Optional[str]:
        """上传临时素材"""
        access_token = await self._get_access_token()
        client = await self._get_client()
        
        url = f"{self.API_BASE}/media/upload?access_token={access_token}&type={media_type}"
        
        files = {"media": ("image.png", data, "image/png")}
        response = await client.post(url, files=files)
        result = response.json()
        
        if result.get("errcode") != 0:
            logger.error(f"上传媒体失败: {result.get('errmsg')}")
            return None
        
        return result.get("media_id")
    
    def verify_callback_url(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        echostr: str
    ) -> str:
        """
        验证回调 URL
        
        企业微信配置回调地址时会调用此接口验证
        """
        return self.crypt.verify_url(msg_signature, timestamp, nonce, echostr)
    
    async def handle_callback(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        body: str
    ) -> str:
        """
        处理回调消息
        
        返回加密后的响应 XML
        """
        try:
            # 解析加密的 XML
            root = ET.fromstring(body)
            encrypt_msg = root.find("Encrypt").text
            
            # 解密消息
            decrypted_xml = self.crypt.decrypt(
                msg_signature, timestamp, nonce, encrypt_msg
            )
            
            # 解析解密后的 XML
            msg_root = ET.fromstring(decrypted_xml)
            msg_type = msg_root.find("MsgType").text
            from_user = msg_root.find("FromUserName").text
            
            # 根据消息类型处理
            if msg_type == "text":
                content = msg_root.find("Content").text
                response = await self._handle_text_message(from_user, content)
            elif msg_type == "event":
                event_type = msg_root.find("Event").text
                response = await self._handle_event(from_user, event_type, msg_root)
            else:
                response = "不支持的消息类型"
            
            # 发送响应（异步发送，不在回调中返回）
            await self.send_text_message(from_user, response)
            
            # 返回空的成功响应
            return ""
            
        except Exception as e:
            logger.error(f"处理回调失败: {e}", exc_info=True)
            return ""
    
    async def _handle_text_message(self, user_id: str, content: str) -> str:
        """处理文本消息"""
        if not self.message_handler:
            return "消息处理器未初始化"
        
        user_msg = UserMessage(
            user_id=user_id,
            platform="wecom",
            content=content
        )
        
        response = await self.message_handler.handle_message(user_msg)
        
        if response.has_error:
            return response.error
        
        # 如果有图片，单独发送
        if response.image:
            await self.send_image_message(user_id, response.image.data)
        
        return response.text or "处理完成"
    
    async def _handle_event(
        self,
        user_id: str,
        event_type: str,
        msg_root: ET.Element
    ) -> str:
        """处理事件"""
        if event_type == "subscribe":
            return "欢迎关注！发送消息即可开始对话。"
        elif event_type == "enter_agent":
            return "欢迎使用加密货币分析助手！"
        else:
            return ""
    
    async def broadcast_message(self, content: str, user_list: Optional[list] = None):
        """
        广播消息
        
        如果 user_list 为空，则发送给所有人
        """
        access_token = await self._get_access_token()
        client = await self._get_client()
        
        url = f"{self.API_BASE}/message/send?access_token={access_token}"
        
        payload = {
            "touser": "|".join(user_list) if user_list else "@all",
            "msgtype": "text",
            "agentid": self.config.agent_id,
            "text": {
                "content": content
            }
        }
        
        response = await client.post(url, json=payload)
        data = response.json()
        
        if data.get("errcode") != 0:
            logger.error(f"广播消息失败: {data.get('errmsg')}")
            return False
        
        return True


class WeComAdapterFactory:
    """企业微信适配器工厂"""
    
    @staticmethod
    def create_from_config(config: Dict[str, Any]) -> Optional[WeComAdapter]:
        """从配置创建适配器"""
        wecom_config = WeComConfig.from_dict(config)
        if not wecom_config:
            logger.warning("企业微信应用配置不完整")
            return None
        
        api_key = config.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("未配置 OPENAI_API_KEY")
            return None
        
        return WeComAdapter(
            config=wecom_config,
            api_key=api_key,
            base_url=config.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=config.get("OPENAI_MODEL", "gpt-4o-mini")
        )


# 全局实例
_wecom_adapter: Optional[WeComAdapter] = None


def get_wecom_adapter() -> Optional[WeComAdapter]:
    """获取全局企业微信适配器"""
    return _wecom_adapter


def init_wecom_adapter(config: Dict[str, Any]) -> Optional[WeComAdapter]:
    """初始化全局企业微信适配器"""
    global _wecom_adapter
    _wecom_adapter = WeComAdapterFactory.create_from_config(config)
    return _wecom_adapter
