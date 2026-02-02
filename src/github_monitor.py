"""
GitHub监控模块 - 获取仓库提交信息
"""

import aiohttp
from datetime import datetime, timezone
from typing import List, Dict, Optional
from loguru import logger


class GitHubMonitor:
    """GitHub仓库监控器"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-QQ-Bot/1.0"
        }
    
    async def get_new_commits(self, repo: str, since: Optional[datetime] = None, last_commit_sha: Optional[str] = None) -> List[Dict]:
        """获取指定时间之后的新提交"""
        url = f"{self.base_url}/repos/{repo}/commits"
        params = {"per_page": 30}  # 增加获取数量以确保不遗漏
        
        if since:
            # 确保时间是UTC格式并添加Z后缀
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            params["since"] = since.strftime('%Y-%m-%dT%H:%M:%SZ')
            logger.info(f"获取 {repo} 自 {params['since']} 以来的提交")
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers, params=params, ssl=False) as response:
                    if response.status == 200:
                        commits_data = await response.json()
                        logger.info(f"从GitHub API获取到 {len(commits_data)} 个提交")
                        
                        # 过滤掉已经处理过的提交
                        if last_commit_sha:
                            new_commits = []
                            for commit in commits_data:
                                if commit["sha"] == last_commit_sha:
                                    break  # 找到上次处理的提交，停止收集
                                new_commits.append(commit)
                            commits_data = new_commits
                            logger.info(f"过滤后得到 {len(commits_data)} 个新提交")
                        
                        # 获取每个提交的详细信息（包括文件变更）
                        detailed_commits = []
                        for commit in commits_data:
                            detailed_commit = await self._get_commit_details(session, repo, commit["sha"])
                            if detailed_commit:
                                detailed_commits.append(detailed_commit)
                        
                        return detailed_commits[::-1]  # 按时间顺序排序（最早的在前）
                    elif response.status == 404:
                        logger.error(f"仓库不存在或无权限访问: {repo}")
                        return []
                    elif response.status == 403:
                        error_msg = await response.text()
                        if "rate limit" in error_msg.lower():
                            logger.error("GitHub API请求频率限制，请稍后重试")
                        else:
                            logger.error("GitHub API访问被限制，请检查token权限")
                        return []
                    else:
                        error_msg = await response.text()
                        logger.error(f"GitHub API请求失败: {response.status}, 响应: {error_msg}")
                        return []
            except aiohttp.ClientError as e:
                logger.error(f"网络请求GitHub API时出错: {e}")
                return []
            except Exception as e:
                logger.error(f"请求GitHub API时出错: {e}")
                return []
    
    async def _get_commit_details(self, session: aiohttp.ClientSession, repo: str, commit_sha: str) -> Optional[Dict]:
        """获取单个提交的详细信息"""
        url = f"{self.base_url}/repos/{repo}/commits/{commit_sha}"
        
        try:
            async with session.get(url, headers=self.headers, ssl=False) as response:
                if response.status == 200:
                    commit_data = await response.json()
                    return self._format_commit(commit_data)
                else:
                    logger.warning(f"获取提交 {commit_sha[:7]} 详情失败: {response.status}")
                    return None
        except Exception as e:
            logger.warning(f"获取提交 {commit_sha[:7]} 详情时出错: {e}")
            return None
    
    async def get_recent_commits(self, repo: str, limit: int = 5) -> List[Dict]:
        """获取最近的提交（用于测试）"""
        url = f"{self.base_url}/repos/{repo}/commits"
        params = {"per_page": limit}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers, params=params, ssl=False) as response:
                    if response.status == 200:
                        commits_data = await response.json()
                        
                        # 获取详细信息
                        detailed_commits = []
                        for commit in commits_data:
                            detailed_commit = await self._get_commit_details(session, repo, commit["sha"])
                            if detailed_commit:
                                detailed_commits.append(detailed_commit)
                        
                        return detailed_commits
                    else:
                        error_msg = await response.text()
                        logger.error(f"获取提交记录失败: {response.status}, 响应: {error_msg}")
                        return []
            except Exception as e:
                logger.error(f"获取提交记录时出错: {e}")
                return []
    
    def _format_commit(self, commit_data: Dict) -> Dict:
        """格式化单个提交数据"""
        try:
            # 解析提交时间并转换为UTC
            commit_date = commit_data["commit"]["author"]["date"]
            parsed_date = datetime.fromisoformat(commit_date.replace('Z', '+00:00'))
            
            formatted_commit = {
                "sha": commit_data["sha"][:7],  # 短SHA
                "full_sha": commit_data["sha"],
                "message": commit_data["commit"]["message"].strip(),
                "author": commit_data["commit"]["author"]["name"],
                "author_email": commit_data["commit"]["author"]["email"],
                "date": parsed_date.isoformat(),
                "url": commit_data["html_url"],
                "stats": {
                    "additions": commit_data.get("stats", {}).get("additions", 0),
                    "deletions": commit_data.get("stats", {}).get("deletions", 0),
                    "total": commit_data.get("stats", {}).get("total", 0)
                }
            }
            
            # 解析提交文件变更
            if "files" in commit_data and commit_data["files"]:
                formatted_commit["files"] = [
                    {
                        "filename": file["filename"],
                        "status": file["status"],  # added, modified, removed
                        "additions": file.get("additions", 0),
                        "deletions": file.get("deletions", 0),
                        "changes": file.get("changes", 0)
                    }
                    for file in commit_data["files"]
                ]
            else:
                formatted_commit["files"] = []
            
            return formatted_commit
            
        except KeyError as e:
            logger.warning(f"提交数据格式异常，缺少字段: {e}")
            return {}
        except Exception as e:
            logger.warning(f"格式化提交数据时出错: {e}")
            return {} 