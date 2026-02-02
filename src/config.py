"""
配置管理模块
"""

import json
from pathlib import Path
from typing import List, Union, Dict, Any
from pydantic import BaseModel, validator


class RepoConfig(BaseModel):
    """仓库配置类"""
    repo: str
    branches: List[str] = ["*"]  # 默认监控所有分支
    
    @validator('repo')
    def validate_repo(cls, v):
        """验证仓库格式"""
        if '/' not in v:
            raise ValueError(f"仓库格式错误: {v}，应为 owner/repo 格式")
        return v


class Config(BaseModel):
    """配置类"""
    
    github_token: str
    github_repos: List[Union[str, Dict[str, Any]]]  # 支持字符串或字典格式
    check_interval: int = 300  # 默认5分钟
    
    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-3.5-turbo"
    
    qq_bot_url: str
    qq_group_id: str
    
    database_path: str = "data.db"
    
    def get_repo_configs(self) -> List[RepoConfig]:
        """获取规范化的仓库配置列表"""
        configs = []
        for item in self.github_repos:
            if isinstance(item, str):
                # 简单字符串格式，默认监控所有分支
                configs.append(RepoConfig(repo=item, branches=["*"]))
            elif isinstance(item, dict):
                repo = item.get('repo')
                if not repo:
                    raise ValueError(f"仓库配置缺少 'repo' 字段: {item}")
                
                # 处理branch和branches字段
                if 'branch' in item:
                    branches = [item['branch']]
                elif 'branches' in item:
                    branches = item['branches'] if isinstance(item['branches'], list) else [item['branches']]
                else:
                    branches = ["*"]  # 默认所有分支
                
                configs.append(RepoConfig(repo=repo, branches=branches))
            else:
                raise ValueError(f"不支持的仓库配置格式: {item}")
        return configs
    
    @validator('github_repos')
    def validate_repos(cls, v):
        """验证仓库格式"""
        if not v:
            raise ValueError("github_repos 不能为空")
        
        for item in v:
            if isinstance(item, str):
                if '/' not in item:
                    raise ValueError(f"仓库格式错误: {item}，应为 owner/repo 格式")
            elif isinstance(item, dict):
                repo = item.get('repo')
                if not repo:
                    raise ValueError(f"仓库配置缺少 'repo' 字段: {item}")
                if '/' not in repo:
                    raise ValueError(f"仓库格式错误: {repo}，应为 owner/repo 格式")
            else:
                raise ValueError(f"不支持的仓库配置格式: {item}")
        return v
    
    @validator('check_interval')
    def validate_interval(cls, v):
        """验证检查间隔"""
        if v < 60:
            raise ValueError("检查间隔不能少于60秒")
        return v
    
    @classmethod
    def from_file(cls, config_path: str) -> 'Config':
        """从配置文件加载配置"""
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        return cls(**config_data) 