"""
数据库模块 - 使用SQLite存储检查状态
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict
from pathlib import Path
from loguru import logger


class Database:
    """简单的SQLite数据库管理"""
    
    def __init__(self, db_path: str = "data.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        try:
            # 确保数据库目录存在
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS repo_checks (
                        repo TEXT PRIMARY KEY,
                        last_check_time TEXT,
                        last_commit_sha TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info(f"数据库初始化完成: {self.db_path}")
        except Exception as e:
            logger.error(f"初始化数据库失败: {e}")
            raise
    
    def get_last_check_time(self, repo: str) -> Optional[datetime]:
        """获取指定仓库的最后检查时间"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT last_check_time FROM repo_checks WHERE repo = ?",
                    (repo,)
                )
                result = cursor.fetchone()
                
                if result and result[0]:
                    # 解析时间并确保是UTC时区
                    dt = datetime.fromisoformat(result[0])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    logger.info(f"获取到仓库 {repo} 的最后检查时间: {dt}")
                    return dt
                    
                logger.info(f"仓库 {repo} 首次检查，没有历史记录")
                return None
        except Exception as e:
            logger.error(f"获取最后检查时间失败: {e}")
            return None
    
    def update_last_check_time(self, repo: str, check_time: datetime, last_commit_sha: str | None = None):
        """更新仓库的最后检查时间和最新提交SHA"""
        try:
            # 确保时间是UTC并格式化为ISO字符串
            if check_time.tzinfo is None:
                check_time = check_time.replace(tzinfo=timezone.utc)
            
            check_time_str = check_time.isoformat()
            current_time = datetime.now(timezone.utc).isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO repo_checks 
                    (repo, last_check_time, last_commit_sha, created_at, updated_at) 
                    VALUES (?, ?, ?, 
                        COALESCE((SELECT created_at FROM repo_checks WHERE repo = ?), ?),
                        ?
                    )
                """, (repo, check_time_str, last_commit_sha, repo, current_time, current_time))
                conn.commit()
                
                logger.info(f"更新仓库 {repo} 检查状态 - 时间: {check_time_str}, SHA: {last_commit_sha[:7] if last_commit_sha else 'None'}")
        except Exception as e:
            logger.error(f"更新最后检查时间失败: {e}")
    
    def get_last_commit_sha(self, repo: str) -> Optional[str]:
        """获取最后处理的提交SHA"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT last_commit_sha FROM repo_checks WHERE repo = ?",
                    (repo,)
                )
                result = cursor.fetchone()
                sha = result[0] if result and result[0] else None
                logger.info(f"获取到仓库 {repo} 的最后提交SHA: {sha[:7] if sha else 'None'}")
                return sha
        except Exception as e:
            logger.error(f"获取最后提交SHA失败: {e}")
            return None
    
    def get_repo_status(self, repo: str) -> Dict:
        """获取仓库的完整状态信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT last_check_time, last_commit_sha, created_at, updated_at FROM repo_checks WHERE repo = ?",
                    (repo,)
                )
                result = cursor.fetchone()
                
                if result:
                    return {
                        "repo": repo,
                        "last_check_time": result[0],
                        "last_commit_sha": result[1],
                        "created_at": result[2],
                        "updated_at": result[3]
                    }
                else:
                    return {"repo": repo, "status": "new"}
        except Exception as e:
            logger.error(f"获取仓库状态失败: {e}")
            return {"repo": repo, "error": str(e)} 