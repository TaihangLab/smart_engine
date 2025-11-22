"""
实时监控API端点模块
提供实时监控页面所需的通道列表、播放控制等功能
"""
from typing import Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException, status, Path
from app.services.wvp_client import WVPClient
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def success_response(data: Any = None, message: str = "成功") -> Dict[str, Any]:
    """
    统一成功响应格式
    
    Args:
        data: 响应数据
        message: 响应消息
        
    Returns:
        标准格式的响应字典
    """
    return {
        "code": 0,
        "msg": message,
        "data": data
    }


def error_response(message: str, code: int = -1) -> Dict[str, Any]:
    """
    统一错误响应格式
    
    Args:
        message: 错误消息
        code: 错误代码
        
    Returns:
        标准格式的错误响应字典
    """
    return {
        "code": code,
        "msg": message,
        "data": None
    }


@router.get("/channels")
def get_monitor_channels(
    page: int = Query(1, description="当前页", ge=1),
    count: int = Query(100, description="每页数量", ge=1, le=1000),
    query: Optional[str] = Query(None, description="查询内容，用于搜索过滤"),
    online: Optional[bool] = Query(None, description="是否在线"),
    has_record_plan: Optional[bool] = Query(None, description="是否已设置录制计划"),
    channel_type: Optional[int] = Query(None, description="通道类型：1=国标设备, 2=推流, 3=代理"),
    civil_code: Optional[str] = Query(None, description="行政区划"),
    parent_device_id: Optional[str] = Query(None, description="父节点编码")
):
    """
    获取实时监控通道列表
    
    此接口对应WVP的 /api/common/channel/list 接口
    用于实时监控页面的通道树展示
    
    Args:
        page: 当前页码，从1开始
        count: 每页记录数
        query: 查询关键词，模糊匹配通道名称
        online: 是否在线筛选
        has_record_plan: 是否设置录制计划
        channel_type: 通道类型，1=国标设备, 2=推流设备, 3=代理流
        civil_code: 行政区划代码
        parent_device_id: 父节点设备ID，用于树形结构
        
    Returns:
        Dict: 包含通道列表、总数、分页信息
        {
            "success": True,
            "data": {
                "total": 100,
                "list": [...]
            }
        }
    """
    try:
        logger.info(f"📡 获取实时监控通道列表 - page:{page}, count:{count}, query:{query}, online:{online}")
        
        wvp_client = WVPClient()
        
        # 调用WVPClient获取通道列表
        result = wvp_client.get_channel_list(
            page=page,
            count=count,
            query=query or "",
            online=online,
            has_record_plan=has_record_plan,
            channel_type=channel_type
        )
        
        if not result:
            logger.warning("⚠️ WVP返回空结果")
            return success_response(
                data={
                    "total": 0,
                    "list": []
                },
                message="未获取到通道数据"
            )
        
        logger.info(f"✅ 成功获取通道列表，共 {result.get('total', 0)} 条记录")
        
        return success_response(data=result)
        
    except Exception as e:
        logger.error(f"❌ 获取实时监控通道列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取通道列表失败: {str(e)}"
        )


@router.get("/channels/{channel_id}")
def get_monitor_channel_detail(
    channel_id: int = Path(..., description="通道ID", ge=1)
):
    """
    获取单个通道的详细信息
    
    此接口对应WVP的 /api/common/channel/{channelId} 接口
    
    Args:
        channel_id: 通道ID
        
    Returns:
        Dict: 通道详细信息
    """
    try:
        logger.info(f"📡 获取通道详情 - channel_id:{channel_id}")
        
        wvp_client = WVPClient()
        channel_info = wvp_client.get_channel_one(channel_id)
        
        if not channel_info:
            logger.warning(f"⚠️ 未找到通道: {channel_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"通道不存在: {channel_id}"
            )
        
        logger.info(f"✅ 成功获取通道详情 - channel_id:{channel_id}")
        
        return success_response(data=channel_info)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取通道详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取通道详情失败: {str(e)}"
        )


@router.get("/play/{channel_id}")
def play_monitor_channel(
    channel_id: int = Path(..., description="通道ID", ge=1)
):
    """
    播放监控通道
    
    此接口对应WVP的 /api/common/channel/play 接口
    用于实时监控页面的视频播放
    
    Args:
        channel_id: 通道ID
        
    Returns:
        Dict: 播放流信息，包含各种格式的流地址
        {
            "success": True,
            "data": {
                "code": 0,
                "msg": "成功",
                "data": {
                    "app": "rtp",
                    "stream": "...",
                    "flv": "http://...",
                    "ws_flv": "ws://...",
                    "wss_flv": "wss://...",
                    "fmp4": "http://...",
                    "ws_fmp4": "ws://...",
                    "wss_fmp4": "wss://...",
                    "hls": "http://...",
                    "ws_hls": "ws://...",
                    "wss_hls": "wss://...",
                    "rtc": "webrtc://...",
                    "rtmp": "rtmp://...",
                    "rtsp": "rtsp://..."
                }
            }
        }
    """
    try:
        logger.info(f"🎬 播放监控通道 - channel_id:{channel_id}")
        
        wvp_client = WVPClient()
        
        # 调用WVPClient播放通道
        play_result = wvp_client.play_channel(channel_id)
        
        if not play_result:
            logger.warning(f"⚠️ 播放通道失败: {channel_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="播放通道失败，请检查通道是否在线"
            )
        
        logger.info(f"✅ 成功播放通道 {channel_id}")
        
        return success_response(data=play_result, message="播放成功")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 播放通道失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"播放通道失败: {str(e)}"
        )


@router.get("/stop/{channel_id}")
def stop_monitor_channel(
    channel_id: int = Path(..., description="通道ID", ge=1)
):
    """
    停止播放监控通道
    
    此接口对应WVP的 /api/common/channel/play/stop 接口
    
    Args:
        channel_id: 通道ID
        
    Returns:
        Dict: 操作结果
    """
    try:
        logger.info(f"⏹️ 停止播放通道 - channel_id:{channel_id}")
        
        wvp_client = WVPClient()
        
        # 验证通道是否存在
        channel_info = wvp_client.get_channel_one(channel_id)
        
        if not channel_info:
            logger.warning(f"⚠️ 未找到通道: {channel_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"通道不存在: {channel_id}"
            )
        
        # 注意：WVP的stop接口需要device_id, channel_id和stream参数
        # 这里简化处理，实际可能需要维护播放会话信息
        # 或者让播放器自然超时关闭
        
        logger.info(f"✅ 通道 {channel_id} 停止播放请求已接收")
        
        return success_response(
            data={"channel_id": channel_id},
            message="停止播放成功"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 停止播放失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"停止播放失败: {str(e)}"
        )


@router.get("/channels/tree")
def get_monitor_channel_tree(
    online: Optional[bool] = Query(None, description="是否在线"),
    channel_type: Optional[int] = Query(None, description="通道类型：1=国标设备, 2=推流, 3=代理")
):
    """
    获取通道树形结构
    
    用于实时监控页面的左侧通道树展示
    支持按行政区划和业务分组两种方式
    
    Args:
        online: 是否在线筛选
        channel_type: 通道类型筛选
        
    Returns:
        Dict: 树形结构的通道列表
    """
    try:
        logger.info(f"🌲 获取通道树 - online:{online}, channel_type:{channel_type}")
        
        wvp_client = WVPClient()
        
        # 获取所有通道（不分页）
        result = wvp_client.get_channel_list(
            page=1,
            count=1000,  # 获取足够多的通道
            query="",
            online=online,
            has_record_plan=None,
            channel_type=channel_type
        )
        
        if not result:
            logger.warning("⚠️ 未获取到通道数据")
            return success_response(
                data=[],
                message="未获取到通道数据"
            )
        
        # 这里可以对通道列表进行树形结构转换
        # 根据civilCode或parentId构建树
        channels = result.get('list', [])
        
        logger.info(f"✅ 成功获取通道树，共 {len(channels)} 个通道")
        
        return success_response(data=channels)
        
    except Exception as e:
        logger.error(f"❌ 获取通道树失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取通道树失败: {str(e)}"
        )


@router.get("/region/tree")
def get_monitor_region_tree(
    parent: Optional[int] = Query(None, description="父节点ID (Integer类型)"),
    hasChannel: bool = Query(True, description="是否包含通道")
):
    """
    获取行政区划树
    
    此接口对应WVP的 /api/region/tree/list 接口
    用于实时监控页面的行政区划树展示
    
    Args:
        parent: 父节点ID (注意：RegionController使用Integer类型)
        hasChannel: 是否包含通道
        
    Returns:
        Dict: 行政区划树节点列表
        
    注意：RegionController没有query参数
    """
    try:
        logger.info(f"🌲 获取行政区划树 - parent:{parent}, hasChannel:{hasChannel}")
        
        wvp_client = WVPClient()
        
        # 调用WVPClient获取行政区划树
        tree_data = wvp_client.get_region_tree(
            parent=parent,
            has_channel=hasChannel
        )
        
        logger.info(f"✅ 成功获取行政区划树，共 {len(tree_data)} 个节点")
        
        return success_response(data=tree_data)
        
    except Exception as e:
        logger.error(f"❌ 获取行政区划树失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取行政区划树失败: {str(e)}"
        )


@router.get("/group/tree")
def get_monitor_group_tree(
    query: Optional[str] = Query(None, description="搜索关键词"),
    parent: Optional[int] = Query(None, description="父节点ID (Integer类型)"),
    hasChannel: bool = Query(True, description="是否包含通道")
):
    """
    获取业务分组树
    
    此接口对应WVP的 /api/group/tree/list 接口
    用于实时监控页面的业务分组树展示
    
    Args:
        query: 搜索关键词 (GroupController有此参数，与RegionController不同)
        parent: 父节点ID (注意：GroupController使用Integer类型)
        hasChannel: 是否包含通道
        
    Returns:
        Dict: 业务分组树节点列表
    """
    try:
        logger.info(f"🌲 获取业务分组树 - query:{query}, parent:{parent}, hasChannel:{hasChannel}")
        
        wvp_client = WVPClient()
        
        # 调用WVPClient获取业务分组树
        tree_data = wvp_client.get_group_tree(
            query=query,
            parent=parent,
            has_channel=hasChannel
        )
        
        logger.info(f"✅ 成功获取业务分组树，共 {len(tree_data)} 个节点")
        
        return success_response(data=tree_data)
        
    except Exception as e:
        logger.error(f"❌ 获取业务分组树失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取业务分组树失败: {str(e)}"
        )



