"""
AI总结模块 - 使用大模型生成提交总结
"""

import openai
from typing import List, Dict
from loguru import logger


class AISummarizer:
    """AI提交总结器"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-3.5-turbo"):
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.model = model
    
    async def summarize_commits(self, repo: str, commits: List[Dict]) -> str:
        """生成提交总结"""
        try:
            # 构建提交信息文本
            commits_text = self._format_commits_for_ai(commits)
            
            # 构建提示词
            prompt = f"""
请帮我总结以下GitHub仓库的提交记录，用中文回答：

仓库：{repo}
提交记录：
{commits_text}

请生成一个简洁的总结，包括：
1. 主要功能更新
2. Bug修复
3. 代码优化
4. 其他重要变更

总结应该简洁明了，适合在QQ群中分享。如果有多个提交，请按重要性排序。
"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的代码提交总结助手，能够简洁明了地总结GitHub提交记录。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800
            )
            summary = response.choices[0].message.content
            if summary:
                summary= summary.strip()
            
            # 添加仓库链接和时间信息
            header = f"📊 {repo} 代码更新总结\n" + "="*30 + "\n"
            footer = f"\n🔗 查看详情：https://github.com/{repo}/commits"
            
            assert summary
            return header + summary + footer
            
        except Exception as e:
            logger.error(f"生成AI总结时出错: {e}")
            # 返回简单的提交列表作为备用
            return self._generate_simple_summary(repo, commits)
    
    def _format_commits_for_ai(self, commits: List[Dict]) -> str:
        """格式化提交记录供AI处理"""
        formatted_commits = []
        
        for commit in commits:
            commit_info = f"""
提交SHA: {commit['sha']}
作者: {commit['author']}
时间: {commit['date']}
消息: {commit['message']}
"""
            
            # 添加文件变更信息
            if 'files' in commit and commit['files']:
                files_info = []
                for file in commit['files'][:5]:  # 最多显示5个文件
                    files_info.append(f"  - {file['filename']} ({file['status']})")
                commit_info += "变更文件:\n" + "\n".join(files_info)
                
                if len(commit['files']) > 5:
                    commit_info += f"\n  ... 还有 {len(commit['files']) - 5} 个文件"
            
            formatted_commits.append(commit_info)
        
        return "\n" + "-"*50 + "\n".join(formatted_commits)
    
    def _generate_simple_summary(self, repo: str, commits: List[Dict]) -> str:
        """生成简单的提交总结（AI失败时的备用方案）"""
        header = f"📊 {repo} 代码更新\n" + "="*20 + "\n"
        
        commits_list = []
        for commit in commits[:3]:  # 最多显示3个提交
            commit_line = f"• {commit['sha']} - {commit['message'][:50]}{'...' if len(commit['message']) > 50 else ''}"
            commits_list.append(commit_line)
        
        if len(commits) > 3:
            commits_list.append(f"... 还有 {len(commits) - 3} 个提交")
        
        footer = f"\n🔗 查看详情：https://github.com/{repo}/commits"
        
        return header + "\n".join(commits_list) + footer 