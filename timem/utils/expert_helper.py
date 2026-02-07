"""
Expert工具模块 - 提供获取所有expert的辅助函数
"""
from typing import List, Optional, Set
from sqlalchemy import text
from timem.utils.logging import get_logger

logger = get_logger(__name__)


async def get_all_experts_for_user(user_id: str) -> List[str]:
    """
    获取与指定用户有交互的所有expert_id

    Args:
        user_id: 用户ID

    Returns:
        expert_id列表
    """
    try:
        from timem.core.global_connection_pool import get_global_pool_manager

        pool_manager = await get_global_pool_manager()

        # 查询该用户交互过的所有expert
        query = text("""
            SELECT DISTINCT expert_id
            FROM core_memories
            WHERE user_id = :user_id
            AND expert_id IS NOT NULL
            ORDER BY expert_id
        """)

        async with pool_manager.get_managed_session() as session:
            result = await session.execute(query, {"user_id": user_id})
            expert_ids = [str(row.expert_id) for row in result]

        logger.debug(f"用户 {user_id} 的expert列表: {expert_ids}")
        return expert_ids

    except Exception as e:
        logger.error(f"获取用户 {user_id} 的expert列表失败: {e}")
        # 返回空列表表示获取失败
        return []


async def get_all_active_experts(days: int = 30) -> List[str]:
    """
    获取最近活跃的所有expert_id

    Args:
        days: 查询最近N天的数据

    Returns:
        expert_id列表
    """
    try:
        from timem.core.global_connection_pool import get_global_pool_manager

        pool_manager = await get_global_pool_manager()

        # 查询最近有活动的expert
        query = text("""
            SELECT DISTINCT expert_id
            FROM core_memories
            WHERE created_at >= NOW() - INTERVAL :days DAY
            AND expert_id IS NOT NULL
            ORDER BY expert_id
        """)

        async with pool_manager.get_managed_session() as session:
            result = await session.execute(query, {"days": days})
            expert_ids = [str(row.expert_id) for row in result]

        logger.info(f"最近{days}天活跃的expert数量: {len(expert_ids)}")
        return expert_ids

    except Exception as e:
        logger.error(f"获取活跃expert列表失败: {e}")
        return []


async def get_active_user_expert_pairs(days: int = 30) -> List[tuple]:
    """
    获取最近活跃的所有用户-expert对

    Args:
        days: 查询最近N天的数据

    Returns:
        [(user_id, expert_id), ...] 列表
    """
    try:
        from timem.core.global_connection_pool import get_global_pool_manager

        pool_manager = await get_global_pool_manager()

        query = text("""
            SELECT DISTINCT user_id, expert_id
            FROM core_memories
            WHERE created_at >= NOW() - INTERVAL :days DAY
            AND expert_id IS NOT NULL
            ORDER BY user_id, expert_id
        """)

        async with pool_manager.get_managed_session() as session:
            result = await session.execute(query, {"days": days})
            pairs = [(str(row.user_id), str(row.expert_id)) for row in result]

        logger.info(f"最近{days}天活跃的用户-expert对数量: {len(pairs)}")
        return pairs

    except Exception as e:
        logger.error(f"获取活跃用户-expert对失败: {e}")
        return []
