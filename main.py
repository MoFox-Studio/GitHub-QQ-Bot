#!/usr/bin/env python3
"""
GitHub QQ Bot - 监控GitHub仓库提交并发送总结到QQ群
"""

import asyncio
import json
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import click
from loguru import logger

from src.github_monitor import GitHubMonitor
from src.ai_summarizer import AISummarizer
from src.qq_bot import QQBot
from src.config import Config, ReleaseMonitorConfig, CIMonitorConfig
from src.database import Database
import ssl

ssl._create_default_https_context = ssl._create_unverified_context


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """GitHub QQ Bot - 自动监控GitHub提交并发送总结到QQ群"""
    pass


@cli.command()
@click.option('--config', '-c', default='config.json', help='配置文件路径')
def run(config):
    """运行监控服务"""
    try:
        # 加载配置
        config_obj = Config.from_file(config)
        
        # 初始化组件
        db = Database(config_obj.database_path)
        github_monitor = GitHubMonitor(config_obj.github_token, proxy=config_obj.proxy)
        ai_summarizer = AISummarizer(
            config_obj.openai_api_key, 
            config_obj.openai_base_url,
            config_obj.openai_model
        )
        qq_bot = QQBot(config_obj.qq_bot_url, config_obj.qq_group_id)
        
        # 获取仓库配置
        repo_configs = config_obj.get_repo_configs()
        
        logger.info("🚀 启动GitHub QQ Bot监控服务...")
        for repo_config in repo_configs:
            branch_info = ", ".join(repo_config.branches) if repo_config.branches != ["*"] else "所有分支"
            logger.info(f"监控仓库: {repo_config.repo} (分支: {branch_info})")
        release_monitor_configs = config_obj.get_release_monitor_configs()
        for repo in release_monitor_configs:
            logger.info(f"监控Release: {repo} (QQ群: {config_obj.qq_group_id})")
        ci_monitor_configs = config_obj.get_ci_monitor_configs()
        for repo in ci_monitor_configs:
            logger.info(f"监控CI构建产物: {repo} (QQ群: {config_obj.qq_group_id})")
        logger.info(f"检查间隔: {config_obj.check_interval}秒")
        
        # 主循环
        while True:
            try:
                # 检查每个仓库
                for repo_config in repo_configs:
                    asyncio.run(process_repo(repo_config, db, github_monitor, ai_summarizer, qq_bot))

                for repo, monitor_config in release_monitor_configs.items():
                    asyncio.run(process_release(repo, monitor_config, db, github_monitor, qq_bot, config_obj.qq_group_id))

                for repo, monitor_config in ci_monitor_configs.items():
                    asyncio.run(process_ci(repo, monitor_config, db, github_monitor, qq_bot, config_obj.qq_group_id))
                
                logger.info(f"💤 等待{config_obj.check_interval}秒后继续检查...")
                time.sleep(config_obj.check_interval)
                
            except KeyboardInterrupt:
                logger.info("👋 收到退出信号，停止服务...")
                break
            except Exception as e:
                logger.error(f"❌ 处理过程中出错: {e}")
                time.sleep(60)  # 出错后等待1分钟再继续
    
    except Exception as e:
        logger.error(f"❌ 启动失败: {e}")
        click.echo(f"错误: {e}", err=True)


async def process_repo(repo_config, db: Database, github_monitor: GitHubMonitor, 
                      ai_summarizer: AISummarizer, qq_bot: QQBot):
    """处理单个仓库的提交检查"""
    repo = repo_config.repo
    branches = repo_config.branches
    
    try:
        branch_info = ", ".join(branches) if branches != ["*"] else "所有分支"
        logger.info(f"🔍 检查仓库 {repo} 的新提交 (分支: {branch_info})...")
        
        # 获取最后检查时间和SHA
        last_check = db.get_last_check_time(repo)
        last_commit_sha = db.get_last_commit_sha(repo)
        
        # 获取新提交（使用SHA过滤避免重复，传递分支配置）
        commits = await github_monitor.get_new_commits(repo, last_check, last_commit_sha, branches)
        
        if not commits:
            logger.info(f"✅ {repo} 没有新提交")
            return
        
        logger.info(f"📝 发现 {len(commits)} 个新提交:")
        for commit in commits:
            logger.info(f"  - {commit['sha']}: {commit['message'][:50]}{'...' if len(commit['message']) > 50 else ''}")
        
        # 生成提交总结
        try:
            summary = await ai_summarizer.summarize_commits(repo, commits)
            logger.info("✅ 生成提交总结完成")
        except Exception as e:
            logger.error(f"❌ 生成提交总结失败: {e}")
            # 如果AI总结失败，发送简单的提交列表
            summary = f"🔄 仓库 {repo} 有 {len(commits)} 个新提交:\n\n"
            for commit in commits[:5]:  # 最多显示5个
                summary += f"• {commit['sha']}: {commit['message'][:100]}{'...' if len(commit['message']) > 100 else ''}\n"
                summary += f"  👤 {commit['author']} | 🔗 {commit['url']}\n\n"
            if len(commits) > 5:
                summary += f"... 还有 {len(commits) - 5} 个提交"
        
        # 发送到QQ群
        try:
            success = await qq_bot.send_message(summary)
            if success:
                logger.info(f"✅ {repo} 的提交总结已发送到QQ群")
                
                # 只有成功发送后才更新数据库
                latest_commit = commits[-1]  # 最新的提交在最后
                db.update_last_check_time(
                    repo, 
                    datetime.now(timezone.utc), 
                    latest_commit['full_sha']
                )
            else:
                logger.error("❌ 发送到QQ群失败，不更新检查时间")
        except Exception as e:
            logger.error(f"❌ 发送QQ消息时出错: {e}")
        
    except Exception as e:
        logger.error(f"❌ 处理仓库 {repo} 时出错: {e}", exc_info=True)


async def process_release(repo: str, monitor_config: ReleaseMonitorConfig, db: Database,
                          github_monitor: GitHubMonitor, qq_bot: QQBot, default_group_id: str) -> None:
    """处理单个仓库的Release检查和QQ群通知。"""

    try:
        logger.info(f"🔍 检查仓库 {repo} 的新Release...")
        release = await github_monitor.get_latest_release(repo, monitor_config.include_prerelease)
        if not release:
            logger.info(f"✅ {repo} 没有可通知的Release")
            return

        release_id = str(release["id"])
        if db.get_last_release_id(repo) == release_id:
            logger.info(f"✅ {repo} Release {release['tag_name']} 已通知过")
            return

        group_id = default_group_id
        files_success = await send_release_assets(
            repo,
            release,
            monitor_config.asset_files,
            github_monitor,
            qq_bot,
            group_id,
            monitor_config.group_file_folder_name,
        )
        if not files_success:
            logger.error("❌ Release文件发送失败，不更新Release状态")
            return

        message = format_release_message(repo, release)
        success = await qq_bot.send_message(message, group_id=group_id)
        if not success:
            logger.error("❌ Release消息发送失败，不更新Release状态")
            return

        db.update_last_release(repo, release_id, release["tag_name"])
    except Exception as e:
        logger.error(f"❌ 处理仓库 {repo} Release时出错: {e}", exc_info=True)


def format_release_message(repo: str, release: dict) -> str:
    """格式化Release通知消息。"""

    note = release.get("body") or "无Release Note"
    return (
        f"🚀 仓库 {repo} 发布了新Release\n"
        f"📌 版本: {release.get('tag_name', '')}\n"
        f"📝 标题: {release.get('name', '')}\n"
        f"🔗 链接: {release.get('url', '')}\n\n"
        f"Release Note:\n{note}"
    )


async def send_release_assets(
    repo: str,
    release: dict,
    asset_files: list[str],
    github_monitor: GitHubMonitor,
    qq_bot: QQBot,
    group_id: str,
    group_file_folder_name: str | None = None,
) -> bool:
    """下载并发送配置中指定的Release资源文件。"""

    if not asset_files:
        return True

    assets = release.get("assets", [])
    for asset_pattern in asset_files:
        matched_assets = match_release_assets(assets, asset_pattern)
        if not matched_assets:
            logger.error(f"Release {release['tag_name']} 中找不到匹配资源文件: {asset_pattern}")
            return False

        for asset in matched_assets:
            asset_name = asset["name"]
            with tempfile.TemporaryDirectory() as temp_dir:
                logger.info(f"📥 下载Release资源文件: {asset_name}...")
                target_path = Path(temp_dir) / asset_name
                downloaded = await github_monitor.download_release_asset(asset["download_url"], target_path)
                if not downloaded:
                    return False
                if not await qq_bot.send_group_file(
                    str(target_path.resolve()),
                    group_id=group_id,
                    name=asset_name,
                    folder_name=group_file_folder_name,
                ):
                    return False

    return True


def match_release_assets(assets: list[dict], asset_pattern: str) -> list[dict]:
    """按精确文件名或正则表达式匹配Release资源文件。"""

    exact_matches = [asset for asset in assets if asset.get("name") == asset_pattern]
    if exact_matches:
        return exact_matches

    try:
        regex = re.compile(asset_pattern)
    except re.error as e:
        logger.error(f"Release资源匹配正则无效: {asset_pattern}, 错误: {e}")
        return []

    return [
        asset
        for asset in assets
        if regex.fullmatch(asset.get("name", ""))
    ]


async def process_ci(repo: str, monitor_config: CIMonitorConfig, db: Database,
                     github_monitor: GitHubMonitor, qq_bot: QQBot, default_group_id: str) -> None:
    """处理单个仓库的CI构建产物检查和QQ群通知。"""

    try:
        logger.info(f"🔍 检查仓库 {repo} 的新CI构建产物...")
        run = await github_monitor.get_latest_workflow_run(
            repo,
            workflow=monitor_config.workflow,
            branch=monitor_config.branch,
            include_in_progress=monitor_config.include_in_progress,
        )
        if not run:
            logger.info(f"✅ {repo} 没有可通知的CI运行")
            return

        run_id = run["run_id"]
        if db.get_last_ci_run_id(repo) == run_id:
            logger.info(f"✅ {repo} CI运行 {run_id} 已处理过")
            return

        group_id = default_group_id
        files_success = await send_ci_artifacts(
            repo,
            run,
            monitor_config.artifact_files,
            github_monitor,
            qq_bot,
            group_id,
            monitor_config.group_file_folder_name,
        )
        if not files_success:
            logger.error("❌ CI构建产物发送失败，不更新CI状态")
            return

        message = format_ci_message(repo, run)
        success = await qq_bot.send_message(message, group_id=group_id)
        if not success:
            logger.error("❌ CI消息发送失败，不更新CI状态")
            return

        db.update_last_ci_run(
            repo,
            run_id,
            run.get("path", ""),
            run.get("head_branch", ""),
            run.get("head_sha", ""),
        )
    except Exception as e:
        logger.error(f"❌ 处理仓库 {repo} CI构建产物时出错: {e}", exc_info=True)


def format_ci_message(repo: str, run: dict) -> str:
    """格式化CI构建产物通知消息。"""

    conclusion = run.get("conclusion", "") or run.get("status", "")
    conclusion_emoji = {
        "success": "✅",
        "failure": "❌",
        "cancelled": "⚠️",
        "skipped": "⏭️",
    }.get(conclusion, "🔄")

    return (
        f"🏗️ 仓库 {repo} 有新的CI构建\n"
        f"{conclusion_emoji} 状态: {conclusion}\n"
        f"📋 工作流: {run.get('path', '') or run.get('name', '')}\n"
        f"🌿 分支: {run.get('head_branch', '')}\n"
        f"🔑 提交: {run.get('head_sha', '')[:7]}\n"
        f"🔗 链接: {run.get('url', '')}\n\n"
        f"构建产物已上传到群文件"
    )


async def send_ci_artifacts(
    repo: str,
    run: dict,
    artifact_files: list[str],
    github_monitor: GitHubMonitor,
    qq_bot: QQBot,
    group_id: str,
    group_file_folder_name: str | None = None,
) -> bool:
    """下载并发送配置中指定的CI构建产物。"""

    if not artifact_files:
        return True

    run_id = int(run["run_id"])
    artifacts = await github_monitor.get_workflow_run_artifacts(repo, run_id)
    if not artifacts:
        logger.error(f"CI运行 {run_id} 没有可下载的构建产物")
        return False

    for artifact_pattern in artifact_files:
        matched_artifacts = match_ci_artifacts(artifacts, artifact_pattern)
        if not matched_artifacts:
            logger.error(f"CI运行 {run_id} 中找不到匹配构建产物: {artifact_pattern}")
            return False

        for artifact in matched_artifacts:
            artifact_name = artifact["name"]
            if artifact.get("expired"):
                logger.error(f"构建产物已过期无法下载: {artifact_name}")
                return False

            with tempfile.TemporaryDirectory() as temp_dir:
                logger.info(f"📥 下载CI构建产物: {artifact_name}...")
                target_path = Path(temp_dir) / f"{artifact_name}.zip"
                downloaded = await github_monitor.download_artifact(
                    repo, artifact["id"], target_path
                )
                if not downloaded:
                    return False
                if not await qq_bot.send_group_file(
                    str(target_path.resolve()),
                    group_id=group_id,
                    name=f"{artifact_name}.zip",
                    folder_name=group_file_folder_name,
                ):
                    return False

    return True


def match_ci_artifacts(artifacts: list[dict], artifact_pattern: str) -> list[dict]:
    """按精确名称或正则表达式匹配CI构建产物。"""

    exact_matches = [artifact for artifact in artifacts if artifact.get("name") == artifact_pattern]
    if exact_matches:
        return exact_matches

    try:
        regex = re.compile(artifact_pattern)
    except re.error as e:
        logger.error(f"CI构建产物匹配正则无效: {artifact_pattern}, 错误: {e}")
        return []

    return [
        artifact
        for artifact in artifacts
        if regex.fullmatch(artifact.get("name", ""))
    ]


@cli.command()
@click.option('--config', '-c', default='config.json', help='配置文件路径')
def init_config(config):
    """初始化配置文件"""
    config_path = Path(config)
    
    if config_path.exists():
        if not click.confirm(f"配置文件 {config} 已存在，是否覆盖？"):
            return
    
    # 创建默认配置
    default_config = {
        "github_token": "",
        "github_repos": [
            {
                "repo": "owner/repo",
                "branch": "main"
            }
        ],
        "check_interval": 300,
        "openai_api_key": "",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-3.5-turbo",
        "qq_bot_url": "http://127.0.0.1:5700",
        "qq_group_id": "",
        "database_path": "data.db",
        "proxy": None,
        "release_monitors": {
            "owner/repo": {
                "asset_files": ["example-.*\\.zip"],
                "include_prerelease": False,
                "group_file_folder_name": "Release"
            }
        },
        "ci_monitors": {
            "owner/repo": {
                "artifact_files": ["build-output"],
                "workflow": "build.yml",
                "branch": "main",
                "include_in_progress": False,
                "group_file_folder_name": "CI"
            }
        },
        "_comment": "仓库配置说明: github_repos支持字符串或对象格式；release_monitors按owner/repo配置Release监视，asset_files填写要发送到全局QQ群的Release资源文件名或正则表达式，group_file_folder_name填写QQ群文件夹名称，留空则上传到群文件根目录；ci_monitors按owner/repo配置CI构建产物监视，artifact_files填写要下载的artifact名称或正则表达式，workflow填写工作流文件名（如build.yml，留空表示所有工作流），branch填写分支名称（留空表示默认分支），include_in_progress是否包含未完成的运行，group_file_folder_name填写QQ群文件夹名称"
    }
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(default_config, f, indent=2, ensure_ascii=False)
    
    click.echo(f"✅ 配置文件已创建: {config}")
    click.echo("请编辑配置文件填入相关信息后运行监控服务")


@cli.command()
@click.argument('repo')
@click.option('--config', '-c', default='config.json', help='配置文件路径')
def test(repo, config):
    """测试指定仓库的监控功能"""
    try:
        config_obj = Config.from_file(config)
        
        # 初始化组件
        github_monitor = GitHubMonitor(config_obj.github_token, proxy=config_obj.proxy)
        ai_summarizer = AISummarizer(
            config_obj.openai_api_key, 
            config_obj.openai_base_url,
            config_obj.openai_model
        )
        
        click.echo(f"🧪 测试仓库: {repo}")
        
        # 获取最近的提交
        commits = asyncio.run(github_monitor.get_recent_commits(repo, limit=3))
        
        if not commits:
            click.echo("没有找到提交记录")
            return
        
        click.echo(f"找到 {len(commits)} 个最近的提交")
        
        # 生成总结
        summary = asyncio.run(ai_summarizer.summarize_commits(repo, commits))
        
        click.echo("\n生成的总结:")
        click.echo("-" * 50)
        click.echo(summary)
        click.echo("-" * 50)
        
    except Exception as e:
        click.echo(f"测试失败: {e}", err=True)


if __name__ == '__main__':
    cli() 