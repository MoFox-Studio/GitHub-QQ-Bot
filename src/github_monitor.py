"""
GitHub监控模块 - 获取仓库提交信息
"""

import aiohttp
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from loguru import logger

try:
    from aiohttp_socks import ProxyConnector as SocksProxyConnector
    _AIOHTTP_SOCKS_AVAILABLE = True
except ImportError:
    SocksProxyConnector = None
    _AIOHTTP_SOCKS_AVAILABLE = False


class GitHubMonitor:
    """GitHub仓库监控器"""
    
    def __init__(self, token: str, proxy: Optional[str] = None):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-QQ-Bot/1.0"
        }
        self.proxy = proxy
        if proxy:
            if proxy.startswith("socks") and not _AIOHTTP_SOCKS_AVAILABLE:
                logger.warning(
                    f"配置了SOCKS代理 {proxy}，但未安装 aiohttp-socks 包，"
                    "SOCKS代理将不可用。请运行: pip install aiohttp-socks"
                )
            else:
                logger.info(f"已启用代理下载加速: {proxy}")

    def _create_session(self) -> aiohttp.ClientSession:
        """创建aiohttp会话，根据代理类型使用合适的连接器。

        - http/https 代理：使用aiohttp原生proxy参数（在请求时传入）
        - socks4/socks5 代理：使用aiohttp-socks的ProxyConnector
        """

        if self.proxy and self.proxy.startswith("socks") and _AIOHTTP_SOCKS_AVAILABLE:
            connector = SocksProxyConnector.from_url(self.proxy)
            return aiohttp.ClientSession(connector=connector)
        return aiohttp.ClientSession()

    def _request_kwargs(self) -> Dict[str, Any]:
        """返回请求级别的代理参数（仅对http/https代理生效）。"""

        if self.proxy and not self.proxy.startswith("socks"):
            return {"proxy": self.proxy}
        return {}
    
    async def get_new_commits(self, repo: str, since: Optional[datetime] = None, last_commit_sha: Optional[str] = None, branches: Optional[List[str]] = None) -> List[Dict]:
        """获取指定时间之后的新提交
        
        Args:
            repo: 仓库名称 (owner/repo)
            since: 起始时间
            last_commit_sha: 上次处理的提交SHA
            branches: 要监控的分支列表，None或["*"]表示所有分支
        """
        # 如果没有指定分支或指定了"*"，则获取所有分支
        if not branches or "*" in branches:
            branches = None  # GitHub API 默认返回所有分支
        
        all_commits = []
        
        # 如果指定了特定分支，分别获取每个分支的提交
        if branches:
            for branch in branches:
                logger.info(f"获取 {repo} 分支 {branch} 的提交")
                branch_commits = await self._get_branch_commits(repo, branch, since, last_commit_sha)
                all_commits.extend(branch_commits)
        else:
            # 获取所有分支的提交（默认行为）
            logger.info(f"获取 {repo} 所有分支的提交")
            all_commits = await self._get_branch_commits(repo, None, since, last_commit_sha)
        
        # 去重（同一个提交可能在多个分支上）
        seen_shas = set()
        unique_commits = []
        for commit in all_commits:
            if commit["full_sha"] not in seen_shas:
                seen_shas.add(commit["full_sha"])
                unique_commits.append(commit)
        
        return unique_commits[::-1]  # 按时间顺序排序（最早的在前）
    
    async def _get_branch_commits(self, repo: str, branch: Optional[str], since: Optional[datetime], last_commit_sha: Optional[str]) -> List[Dict]:
        """获取指定分支的提交"""
        url = f"{self.base_url}/repos/{repo}/commits"
        params: Dict[str, Any] = {"per_page": 30}  # 增加获取数量以确保不遗漏
        
        # 添加分支参数
        if branch:
            params["sha"] = branch
        
        if since:
            # 确保时间是UTC格式并添加Z后缀
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            params["since"] = since.strftime('%Y-%m-%dT%H:%M:%SZ')
            branch_info = f"分支 {branch}" if branch else "所有分支"
            logger.info(f"获取 {repo} {branch_info} 自 {params['since']} 以来的提交")
        
        async with self._create_session() as session:
            try:
                async with session.get(url, headers=self.headers, params=params, ssl=False, **self._request_kwargs()) as response:
                    if response.status == 200:
                        commits_data = await response.json()
                        branch_info = f"分支 {branch}" if branch else "所有分支"
                        logger.info(f"从GitHub API获取到 {len(commits_data)} 个提交 ({branch_info})")
                        
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
                        
                        return detailed_commits
                    elif response.status == 404:
                        branch_info = f"或分支 {branch} 不存在" if branch else ""
                        logger.error(f"仓库不存在或无权限访问: {repo}{branch_info}")
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
            async with session.get(url, headers=self.headers, ssl=False, **self._request_kwargs()) as response:
                if response.status == 200:
                    commit_data = await response.json()
                    return self._format_commit(commit_data)
                else:
                    logger.warning(f"获取提交 {commit_sha[:7]} 详情失败: {response.status}")
                    return None
        except Exception as e:
            logger.warning(f"获取提交 {commit_sha[:7]} 详情时出错: {e}")
            return None
    

    async def get_latest_release(self, repo: str, include_prerelease: bool = False) -> Optional[Dict]:
        """获取仓库最新Release信息。

        Args:
            repo: 仓库名称 (owner/repo)
            include_prerelease: 是否允许预发布版本
        """

        url = f"{self.base_url}/repos/{repo}/releases"
        params: Dict[str, Any] = {"per_page": 10}

        async with self._create_session() as session:
            try:
                async with session.get(url, headers=self.headers, params=params, ssl=False, **self._request_kwargs()) as response:
                    if response.status == 200:
                        releases_data = await response.json()
                        for release_data in releases_data:
                            if release_data.get("draft"):
                                continue
                            if release_data.get("prerelease") and not include_prerelease:
                                continue
                            return self._format_release(release_data)

                        logger.info(f"仓库 {repo} 没有可通知的Release")
                        return None
                    if response.status == 404:
                        logger.error(f"仓库不存在、无权限访问或没有Release: {repo}")
                        return None

                    error_msg = await response.text()
                    logger.error(f"获取Release失败: {response.status}, 响应: {error_msg}")
                    return None
            except aiohttp.ClientError as e:
                logger.error(f"网络请求GitHub Release API时出错: {e}")
                return None
            except Exception as e:
                logger.error(f"请求GitHub Release API时出错: {e}")
                return None

    def _format_release(self, release_data: Dict) -> Dict:
        """格式化单个Release数据。"""

        published_at = release_data.get("published_at")
        parsed_date = None
        if published_at:
            parsed_date = datetime.fromisoformat(published_at.replace('Z', '+00:00')).isoformat()

        return {
            "id": release_data["id"],
            "tag_name": release_data.get("tag_name", ""),
            "name": release_data.get("name") or release_data.get("tag_name", ""),
            "body": release_data.get("body") or "",
            "url": release_data.get("html_url", ""),
            "published_at": parsed_date,
            "prerelease": release_data.get("prerelease", False),
            "assets": [
                {
                    "name": asset.get("name", ""),
                    "download_url": asset.get("browser_download_url", ""),
                    "size": asset.get("size", 0),
                }
                for asset in release_data.get("assets", [])
            ],
        }


    async def download_release_asset(self, download_url: str, target_path: Any) -> bool:
        """下载Release资源文件到本地路径。

        Args:
            download_url: Release资源下载链接
            target_path: 本地保存路径
        """

        try:
            async with self._create_session() as session:
                async with session.get(download_url, headers=self.headers, ssl=False, **self._request_kwargs()) as response:
                    if response.status != 200:
                        error_msg = await response.text()
                        logger.error(f"下载Release资源失败: {response.status}, 响应: {error_msg}")
                        return False

                    with open(target_path, "wb") as file:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            logger.info(f"正在下载Release资源: {target_path}，已下载 {file.tell() / (1024 * 1024):.2f} MB")
                            file.write(chunk)
                    logger.info(f"Release资源下载完成: {target_path}")
                    return True
        except Exception as e:
            logger.error(f"下载Release资源时出错: {e}")
            return False

    async def get_latest_workflow_run(self, repo: str, workflow: Optional[str] = None,
                                       branch: Optional[str] = None,
                                       include_in_progress: bool = False) -> Optional[Dict]:
        """获取仓库最新的已完成Workflow运行。

        Args:
            repo: 仓库名称 (owner/repo)
            workflow: 工作流文件名（如 "build.yml"），None表示所有工作流
            branch: 分支名称，None表示默认分支
            include_in_progress: 是否包含未完成的运行

        Returns:
            格式化后的Workflow运行信息，没有新运行时返回None
        """

        url = f"{self.base_url}/repos/{repo}/actions/runs"
        params: Dict[str, Any] = {"per_page": 30}

        if workflow:
            params["event"] = None  # 不按事件过滤
        if branch:
            params["branch"] = branch

        # 只查询已完成的运行，除非显式要求包含进行中的
        if not include_in_progress:
            params["status"] = "completed"

        async with self._create_session() as session:
            try:
                async with session.get(url, headers=self.headers, params=params, ssl=False, **self._request_kwargs()) as response:
                    if response.status == 200:
                        data = await response.json()
                        runs = data.get("workflow_runs", [])
                        if not runs:
                            logger.info(f"仓库 {repo} 没有可通知的Workflow运行")
                            return None

                        for run in runs:
                            # 按工作流文件名过滤
                            if workflow:
                                run_workflow = run.get("path", "") or run.get("name", "")
                                if workflow not in run_workflow and not run_workflow.endswith(workflow):
                                    continue

                            # 按完成状态过滤
                            if not include_in_progress and run.get("status") != "completed":
                                continue

                            return self._format_workflow_run(run)

                        logger.info(f"仓库 {repo} 没有匹配的Workflow运行")
                        return None
                    if response.status == 404:
                        logger.error(f"仓库不存在或无权限访问Workflow: {repo}")
                        return None

                    error_msg = await response.text()
                    logger.error(f"获取Workflow运行失败: {response.status}, 响应: {error_msg}")
                    return None
            except aiohttp.ClientError as e:
                logger.error(f"网络请求GitHub Actions API时出错: {e}")
                return None
            except Exception as e:
                logger.error(f"请求GitHub Actions API时出错: {e}")
                return None

    def _format_workflow_run(self, run_data: Dict) -> Dict:
        """格式化单个Workflow运行数据。"""

        created_at = run_data.get("created_at")
        parsed_created = None
        if created_at:
            parsed_created = datetime.fromisoformat(created_at.replace('Z', '+00:00')).isoformat()

        updated_at = run_data.get("updated_at")
        parsed_updated = None
        if updated_at:
            parsed_updated = datetime.fromisoformat(updated_at.replace('Z', '+00:00')).isoformat()

        return {
            "id": run_data["id"],
            "run_id": str(run_data["id"]),
            "name": run_data.get("name", ""),
            "workflow_id": run_data.get("workflow_id"),
            "path": run_data.get("path", ""),
            "head_branch": run_data.get("head_branch", ""),
            "head_sha": run_data.get("head_sha", ""),
            "status": run_data.get("status", ""),
            "conclusion": run_data.get("conclusion", ""),
            "url": run_data.get("html_url", ""),
            "created_at": parsed_created,
            "updated_at": parsed_updated,
            "artifacts_url": run_data.get("artifacts_url", ""),
        }

    async def get_workflow_run_artifacts(self, repo: str, run_id: int) -> List[Dict]:
        """获取指定Workflow运行的构建产物列表。

        Args:
            repo: 仓库名称 (owner/repo)
            run_id: Workflow运行ID

        Returns:
            构建产物信息列表
        """

        url = f"{self.base_url}/repos/{repo}/actions/runs/{run_id}/artifacts"

        async with self._create_session() as session:
            try:
                async with session.get(url, headers=self.headers, ssl=False, **self._request_kwargs()) as response:
                    if response.status == 200:
                        data = await response.json()
                        artifacts = data.get("artifacts", [])
                        logger.info(f"获取到Workflow运行 {run_id} 的 {len(artifacts)} 个构建产物")
                        return [
                            {
                                "name": artifact.get("name", ""),
                                "id": artifact.get("id"),
                                "size_in_bytes": artifact.get("size_in_bytes", 0),
                                "url": artifact.get("url", ""),
                                "archive_download_url": artifact.get("archive_download_url", ""),
                                "expired": artifact.get("expired", False),
                            }
                            for artifact in artifacts
                        ]
                    if response.status == 404:
                        logger.error(f"Workflow运行不存在或无权限访问: {repo} run_id={run_id}")
                        return []

                    error_msg = await response.text()
                    logger.error(f"获取构建产物失败: {response.status}, 响应: {error_msg}")
                    return []
            except aiohttp.ClientError as e:
                logger.error(f"网络请求构建产物API时出错: {e}")
                return []
            except Exception as e:
                logger.error(f"请求构建产物API时出错: {e}")
                return []

    async def download_artifact(self, repo: str, artifact_id: int, target_path: Any) -> bool:
        """下载CI构建产物（zip格式）到本地路径。

        Args:
            repo: 仓库名称 (owner/repo)
            artifact_id: 构建产物ID
            target_path: 本地保存路径

        Returns:
            下载是否成功
        """

        url = f"{self.base_url}/repos/{repo}/actions/artifacts/{artifact_id}/zip"

        try:
            async with self._create_session() as session:
                async with session.get(url, headers=self.headers, ssl=False, **self._request_kwargs()) as response:
                    if response.status != 200:
                        error_msg = await response.text()
                        logger.error(f"下载构建产物失败: {response.status}, 响应: {error_msg}")
                        return False

                    with open(target_path, "wb") as file:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            logger.info(f"正在下载构建产物: {target_path}，已下载 {file.tell() / (1024 * 1024):.2f} MB")
                            file.write(chunk)
                    logger.info(f"构建产物下载完成: {target_path}")
                    return True
        except Exception as e:
            logger.error(f"下载构建产物时出错: {e}")
            return False

    async def get_recent_commits(self, repo: str, limit: int = 5, branch: Optional[str] = None) -> List[Dict]:
        """获取最近的提交（用于测试）
        
        Args:
            repo: 仓库名称
            limit: 获取数量
            branch: 分支名称，None表示默认分支
        """
        url = f"{self.base_url}/repos/{repo}/commits"
        params: Dict[str, Any] = {"per_page": limit}
        
        if branch:
            params["sha"] = branch
        
        async with self._create_session() as session:
            try:
                async with session.get(url, headers=self.headers, params=params, ssl=False, **self._request_kwargs()) as response:
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