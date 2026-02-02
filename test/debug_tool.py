#!/usr/bin/env python3
"""
GitHub QQ Bot 调试工具 - 用于诊断提交识别问题
"""

import asyncio
from datetime import datetime, timezone, timedelta

from src.github_monitor import GitHubMonitor
from src.database import Database
from src.config import Config


async def diagnose_repo(config_path: str, repo: str):
    """诊断指定仓库的提交识别问题"""
    
    # 加载配置
    config = Config.from_file(config_path)
    
    # 初始化组件
    github_monitor = GitHubMonitor(config.github_token)
    db = Database(config.database_path)
    
    print(f"🔍 诊断仓库: {repo}")
    print("=" * 60)
    
    # 1. 检查数据库状态
    print("\n📊 数据库状态:")
    status = db.get_repo_status(repo)
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    last_check = db.get_last_check_time(repo)
    last_sha = db.get_last_commit_sha(repo)
    
    # 2. 测试GitHub API连接
    print("\n🔗 测试GitHub API连接:")
    recent_commits = await github_monitor.get_recent_commits(repo, limit=3)
    if recent_commits:
        print(f"  ✅ 成功获取到 {len(recent_commits)} 个最近提交")
        for i, commit in enumerate(recent_commits):
            print(f"    {i+1}. {commit['sha']}: {commit['message'][:50]}{'...' if len(commit['message']) > 50 else ''}")
            print(f"       👤 {commit['author']} | 📅 {commit['date']}")
    else:
        print("  ❌ 无法获取提交，请检查GitHub token和仓库权限")
        return
    
    # 查找对应的仓库配置
    repo_configs = config.get_repo_configs()
    repo_config = None
    for rc in repo_configs:
        if rc.repo == repo:
            repo_config = rc
            break
    
    branches = repo_config.branches if repo_config else ["*"]
    branch_info = ", ".join(branches) if branches != ["*"] else "所有分支"
    print(f"  🌱 配置的分支: {branch_info}")
    
    # 3. 检查新提交检测
    print("\n🆕 检查新提交检测:")
    new_commits = await github_monitor.get_new_commits(repo, last_check, last_sha, branches)
    if new_commits:
        print(f"  📝 发现 {len(new_commits)} 个新提交:")
        for commit in new_commits:
            print(f"    • {commit['sha']}: {commit['message'][:50]}{'...' if len(commit['message']) > 50 else ''}")
            print(f"      👤 {commit['author']} | 📅 {commit['date']}")
            if commit['files']:
                print(f"      📁 修改了 {len(commit['files'])} 个文件")
                for file in commit['files'][:3]:  # 只显示前3个文件
                    print(f"        - {file['filename']} ({file['status']})")
            else:
                print("      📁 文件信息未获取")
    else:
        print("  ✅ 没有新提交")
    
    # 4. 时间比较分析
    print("\n⏰ 时间分析:")
    if last_check:
        print(f"  最后检查时间: {last_check}")
        print(f"  当前UTC时间: {datetime.now(timezone.utc)}")
        
        # 检查最近几小时是否有提交
        for hours in [1, 6, 24]:
            since_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            commits = await github_monitor.get_new_commits(repo, since_time)
            print(f"  最近{hours}小时内提交数: {len(commits) if commits else 0}")
    else:
        print("  这是首次检查，没有历史记录")
    
    # 5. 建议的修复措施
    print("\n💡 建议:")
    if not new_commits and recent_commits:
        print("  1. 如果您刚才提交了代码但机器人没检测到，可能是:")
        print("     - 提交时间早于最后检查时间")
        print("     - 提交SHA已被处理过")
        print("     - 时区设置问题")
        print("  2. 可以尝试重置数据库记录:")
        print(f"     python debug_tool.py --reset {repo}")


async def reset_repo_status(config_path: str, repo: str):
    """重置仓库检查状态"""
    config = Config.from_file(config_path)
    db = Database(config.database_path)
    
    # 删除旧记录
    import sqlite3
    with sqlite3.connect(config.database_path) as conn:
        conn.execute("DELETE FROM repo_checks WHERE repo = ?", (repo,))
        conn.commit()
    
    print(f"✅ 已重置仓库 {repo} 的检查状态")
    print("下次运行时将从最新提交开始检查")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("用法:")
        print("  诊断: python debug_tool.py <config.json> <owner/repo>")
        print("  重置: python debug_tool.py --reset <owner/repo> [config.json]")
        sys.exit(1)
    
    if sys.argv[1] == "--reset":
        repo = sys.argv[2]
        config_path = sys.argv[3] if len(sys.argv) > 3 else "config.json"
        asyncio.run(reset_repo_status(config_path, repo))
    else:
        config_path = sys.argv[1]
        repo = sys.argv[2]
        asyncio.run(diagnose_repo(config_path, repo)) 