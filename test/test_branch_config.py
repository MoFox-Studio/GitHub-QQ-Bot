#!/usr/bin/env python3
"""
测试分支配置功能
"""
import sys
sys.path.append("..")
from src.config import Config

def test_config_parsing():
    """测试配置解析"""
    
    print("=" * 60)
    print("测试分支配置功能")
    print("=" * 60)
    
    # 测试用例1: 简单字符串格式
    print("\n【测试1】简单字符串格式（默认所有分支）")
    config1 = {
        "github_token": "test_token",
        "github_repos": ["owner/repo1", "owner/repo2"],
        "openai_api_key": "test_key",
        "qq_bot_url": "http://localhost",
        "qq_group_id": "123"
    }
    
    config_obj1 = Config(**config1)
    repo_configs1 = config_obj1.get_repo_configs()
    
    for rc in repo_configs1:
        branch_info = ", ".join(rc.branches) if rc.branches != ["*"] else "所有分支"
        print(f"  仓库: {rc.repo}, 分支: {branch_info}")
    
    assert len(repo_configs1) == 2
    assert repo_configs1[0].repo == "owner/repo1"
    assert repo_configs1[0].branches == ["*"]
    print("  ✅ 测试通过")
    
    # 测试用例2: 单个分支配置
    print("\n【测试2】单个分支配置")
    config2 = {
        "github_token": "test_token",
        "github_repos": [
            {"repo": "owner/repo1", "branch": "main"},
            {"repo": "owner/repo2", "branch": "develop"}
        ],
        "openai_api_key": "test_key",
        "qq_bot_url": "http://localhost",
        "qq_group_id": "123"
    }
    
    config_obj2 = Config(**config2)
    repo_configs2 = config_obj2.get_repo_configs()
    
    for rc in repo_configs2:
        branch_info = ", ".join(rc.branches) if rc.branches != ["*"] else "所有分支"
        print(f"  仓库: {rc.repo}, 分支: {branch_info}")
    
    assert repo_configs2[0].branches == ["main"]
    assert repo_configs2[1].branches == ["develop"]
    print("  ✅ 测试通过")
    
    # 测试用例3: 多个分支配置
    print("\n【测试3】多个分支配置")
    config3 = {
        "github_token": "test_token",
        "github_repos": [
            {"repo": "owner/repo1", "branches": ["main", "dev", "release"]}
        ],
        "openai_api_key": "test_key",
        "qq_bot_url": "http://localhost",
        "qq_group_id": "123"
    }
    
    config_obj3 = Config(**config3)
    repo_configs3 = config_obj3.get_repo_configs()
    
    for rc in repo_configs3:
        branch_info = ", ".join(rc.branches) if rc.branches != ["*"] else "所有分支"
        print(f"  仓库: {rc.repo}, 分支: {branch_info}")
    
    assert repo_configs3[0].branches == ["main", "dev", "release"]
    print("  ✅ 测试通过")
    
    # 测试用例4: 通配符配置
    print("\n【测试4】通配符配置（所有分支）")
    config4 = {
        "github_token": "test_token",
        "github_repos": [
            {"repo": "owner/repo1", "branch": "*"}
        ],
        "openai_api_key": "test_key",
        "qq_bot_url": "http://localhost",
        "qq_group_id": "123"
    }
    
    config_obj4 = Config(**config4)
    repo_configs4 = config_obj4.get_repo_configs()
    
    for rc in repo_configs4:
        branch_info = ", ".join(rc.branches) if rc.branches != ["*"] else "所有分支"
        print(f"  仓库: {rc.repo}, 分支: {branch_info}")
    
    assert repo_configs4[0].branches == ["*"]
    print("  ✅ 测试通过")
    
    # 测试用例5: 混合配置
    print("\n【测试5】混合配置")
    config5 = {
        "github_token": "test_token",
        "github_repos": [
            "owner/repo1",
            {"repo": "owner/repo2", "branch": "main"},
            {"repo": "owner/repo3", "branches": ["main", "dev"]},
            {"repo": "owner/repo4", "branch": "*"}
        ],
        "openai_api_key": "test_key",
        "qq_bot_url": "http://localhost",
        "qq_group_id": "123"
    }
    
    config_obj5 = Config(**config5)
    repo_configs5 = config_obj5.get_repo_configs()
    
    for rc in repo_configs5:
        branch_info = ", ".join(rc.branches) if rc.branches != ["*"] else "所有分支"
        print(f"  仓库: {rc.repo}, 分支: {branch_info}")
    
    assert len(repo_configs5) == 4
    assert repo_configs5[0].branches == ["*"]  # 简单字符串
    assert repo_configs5[1].branches == ["main"]  # 单个分支
    assert repo_configs5[2].branches == ["main", "dev"]  # 多个分支
    assert repo_configs5[3].branches == ["*"]  # 通配符
    print("  ✅ 测试通过")
    
    # 测试用例6: 错误处理 - 无效仓库格式
    print("\n【测试6】错误处理 - 无效仓库格式")
    try:
        config6 = {
            "github_token": "test_token",
            "github_repos": ["invalid_repo"],  # 缺少 owner/
            "openai_api_key": "test_key",
            "qq_bot_url": "http://localhost",
            "qq_group_id": "123"
        }
        config_obj6 = Config(**config6)
        print("  ❌ 应该抛出异常")
    except ValueError as e:
        print(f"  ✅ 正确捕获异常: {e}")
    
    # 测试用例7: 错误处理 - 缺少repo字段
    print("\n【测试7】错误处理 - 缺少repo字段")
    try:
        config7 = {
            "github_token": "test_token",
            "github_repos": [{"branch": "main"}],  # 缺少 repo 字段
            "openai_api_key": "test_key",
            "qq_bot_url": "http://localhost",
            "qq_group_id": "123"
        }
        config_obj7 = Config(**config7)
        print("  ❌ 应该抛出异常")
    except ValueError as e:
        print(f"  ✅ 正确捕获异常: {e}")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    test_config_parsing()
