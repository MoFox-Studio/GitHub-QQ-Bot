"""
QQ机器人模块 - 发送消息和文件到QQ群
"""

from typing import Optional

import aiohttp
from loguru import logger


class QQBot:
    """QQ机器人消息和文件发送器。"""
    
    def __init__(self, bot_url: str, group_id: str, token: Optional[str] = None):
        self.bot_url = bot_url.rstrip('/')
        self.group_id = group_id
        self.token = token
        
        # 设置请求头
        self.headers = {
            "Content-Type": "application/json"
        }
        
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
    
    async def send_message(self, message: str, group_id: Optional[str] = None) -> bool:
        """发送消息到QQ群。"""
        try:
            # go-cqhttp API格式
            url = f"{self.bot_url}/send_group_msg"
            
            payload = {
                "group_id": int(group_id or self.group_id),
                "message": message
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("status") == "ok":
                            logger.info("✅ 消息发送成功")
                            return True
                        else:
                            logger.error(f"QQ机器人返回错误: {result}")
                            return False
                    else:
                        logger.error(f"发送消息失败，HTTP状态码: {response.status}")
                        response_text = await response.text()
                        logger.error(f"响应内容: {response_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"发送QQ消息时出错: {e}")
            return False

    async def resolve_group_folder_id(self, folder_name: str, group_id: Optional[str] = None) -> Optional[str]:
        """根据QQ群文件夹名称解析NapCat上传所需的文件夹ID。"""

        try:
            url = f"{self.bot_url}/get_group_root_files"
            payload = {
                "group_id": int(group_id or self.group_id),
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"获取QQ群根目录文件失败，HTTP状态码: {response.status}")
                        response_text = await response.text()
                        logger.error(f"响应内容: {response_text}")
                        return None

                    result = await response.json()
                    if result.get("status") != "ok":
                        logger.error(f"QQ机器人返回错误: {result}")
                        return None

            folders = result.get("data", {}).get("folders", [])
            matched_folders = [
                folder
                for folder in folders
                if folder.get("folder_name") == folder_name or folder.get("name") == folder_name
            ]

            if not matched_folders:
                logger.error(f"QQ群文件夹不存在: {folder_name}")
                return None

            if len(matched_folders) > 1:
                logger.error(f"QQ群文件夹名称重复，无法唯一定位: {folder_name}")
                return None

            folder = matched_folders[0]
            folder_id = folder.get("folder_id") or folder.get("id")
            if not folder_id:
                logger.error(f"QQ群文件夹缺少ID字段: {folder}")
                return None

            logger.info(f"✅ 已解析QQ群文件夹: {folder_name} -> {folder_id}")
            return str(folder_id)
        except Exception as e:
            logger.error(f"解析QQ群文件夹ID时出错: {e}")
            return None

    async def send_group_file(
        self,
        file_path: str,
        group_id: Optional[str] = None,
        name: Optional[str] = None,
        folder_name: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> bool:
        """发送本地文件到QQ群，可按NapCat群文件夹名称上传到指定文件夹。"""

        try:
            target_folder_id = folder_id
            if folder_name:
                target_folder_id = await self.resolve_group_folder_id(folder_name, group_id=group_id)
                if not target_folder_id:
                    return False

            url = f"{self.bot_url}/upload_group_file"
            payload = {
                "group_id": int(group_id or self.group_id),
                "file": file_path,
                "name": name,
            }
            if target_folder_id:
                payload["folder"] = target_folder_id

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("status") == "ok":
                            logger.info(f"✅ 文件发送成功: {name or file_path}")
                            return True
                        logger.error(f"QQ机器人返回错误: {result}")
                        return False

                    logger.error(f"发送文件失败，HTTP状态码: {response.status}")
                    response_text = await response.text()
                    logger.error(f"响应内容: {response_text}")
                    return False
        except Exception as e:
            logger.error(f"发送QQ群文件时出错: {e}")
            return False

    async def send_private_message(self, user_id: str, message: str) -> bool:
        """发送私聊消息"""
        try:
            url = f"{self.bot_url}/send_private_msg"
            
            payload = {
                "user_id": int(user_id),
                "message": message
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("status") == "ok":
                            logger.info("✅ 私聊消息发送成功")
                            return True
                        else:
                            logger.error(f"QQ机器人返回错误: {result}")
                            return False
                    else:
                        logger.error(f"发送私聊消息失败，HTTP状态码: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"发送QQ私聊消息时出错: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """测试QQ机器人连接"""
        try:
            url = f"{self.bot_url}/get_status"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"QQ机器人状态: {result}")
                        return True
                    else:
                        logger.error(f"QQ机器人连接失败: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"测试QQ机器人连接时出错: {e}")
            return False 
