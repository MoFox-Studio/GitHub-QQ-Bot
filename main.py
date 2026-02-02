#!/usr/bin/env python3
"""
GitHub QQ Bot - 监控GitHub仓库提交并发送总结到QQ群
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import click
from loguru import logger
from dotenv import load_dotenv

from src.github_monitor import GitHubMonitor
from src.ai_summarizer import AISummarizer
from src.qq_bot import QQBot
from src.config import Config
from src.database import Database
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

# 加载环境变量
load_dotenv()


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
        github_monitor = GitHubMonitor(config_obj.github_token)
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
        logger.info(f"检查间隔: {config_obj.check_interval}秒")
        
        # 主循环
        while True:
            try:
                # 检查每个仓库
                for repo_config in repo_configs:
                    asyncio.run(process_repo(repo_config, db, github_monitor, ai_summarizer, qq_bot))
                
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
        "_comment": "仓库配置说明: 可以是简单字符串(默认监控所有分支)，或对象格式指定branch(单个分支)/branches(多个分支)。使用'*'表示所有分支"
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
        github_monitor = GitHubMonitor(config_obj.github_token)
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