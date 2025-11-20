"""
知识库服务 - 用于RAG（检索增强生成）
"""
import logging
import json
import os
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """
    知识库服务
    
    功能：
    1. 存储煤矿安全规范
    2. 存储作业流程定义
    3. 支持关键词检索
    4. 返回相关规范和检查清单
    """
    
    # 知识库数据目录
    KB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "knowledge_base")
    
    def __init__(self, kb_name: str = "coalmine_safety_regulations"):
        """
        初始化知识库服务
        
        Args:
            kb_name: 知识库名称
        """
        self.kb_name = kb_name
        self.regulations = {}
        self.task_definitions = {}
        
        # 确保知识库目录存在
        os.makedirs(self.KB_DIR, exist_ok=True)
        
        # 加载知识库
        self._load_knowledge_base()
        
        logger.info(f"知识库服务初始化: {kb_name}, "
                   f"规范数量={len(self.regulations)}, "
                   f"任务定义数量={len(self.task_definitions)}")
    
    def _load_knowledge_base(self):
        """从文件加载知识库"""
        try:
            # 加载安全规范
            regulations_file = os.path.join(self.KB_DIR, "safety_regulations.json")
            if os.path.exists(regulations_file):
                with open(regulations_file, 'r', encoding='utf-8') as f:
                    self.regulations = json.load(f)
            else:
                # 使用默认规范
                self.regulations = self._get_default_regulations()
                # 保存默认规范
                with open(regulations_file, 'w', encoding='utf-8') as f:
                    json.dump(self.regulations, f, ensure_ascii=False, indent=2)
            
            # 加载任务定义
            tasks_file = os.path.join(self.KB_DIR, "task_definitions.json")
            if os.path.exists(tasks_file):
                with open(tasks_file, 'r', encoding='utf-8') as f:
                    self.task_definitions = json.load(f)
            else:
                # 使用默认任务定义
                self.task_definitions = self._get_default_task_definitions()
                # 保存默认任务定义
                with open(tasks_file, 'w', encoding='utf-8') as f:
                    json.dump(self.task_definitions, f, ensure_ascii=False, indent=2)
                    
        except Exception as e:
            logger.error(f"加载知识库失败: {str(e)}")
            # 使用默认数据
            self.regulations = self._get_default_regulations()
            self.task_definitions = self._get_default_task_definitions()
    
    def _get_default_regulations(self) -> Dict[str, Any]:
        """获取默认安全规范"""
        return {
            "受限空间作业": {
                "regulation_id": "CSR-001",
                "title": "受限空间作业安全管理规定",
                "description": "煤矿井下受限空间作业的安全要求和操作规范",
                "requirements": [
                    {
                        "id": "REQ-001",
                        "category": "作业审批",
                        "content": "必须办理受限空间作业票，经安全部门审批后方可作业",
                        "severity": "critical"
                    },
                    {
                        "id": "REQ-002",
                        "category": "气体检测",
                        "content": "作业前必须进行气体检测，氧气含量18-23%，有毒有害气体不超标",
                        "severity": "critical"
                    },
                    {
                        "id": "REQ-003",
                        "category": "通风措施",
                        "content": "必须采取强制通风措施，确保空气流通",
                        "severity": "high"
                    },
                    {
                        "id": "REQ-004",
                        "category": "防护装备",
                        "content": "作业人员必须佩戴防毒面具、安全绳等防护装备",
                        "severity": "critical"
                    },
                    {
                        "id": "REQ-005",
                        "category": "监护人员",
                        "content": "必须设置专人在受限空间外监护，不得擅自离开",
                        "severity": "critical"
                    },
                    {
                        "id": "REQ-006",
                        "category": "应急设备",
                        "content": "现场必须配备救援三脚架、应急呼吸器等应急救援设备",
                        "severity": "high"
                    },
                    {
                        "id": "REQ-007",
                        "category": "人数管理",
                        "content": "严格控制进入人数，做好进出人员登记，确保人数一致",
                        "severity": "high"
                    }
                ]
            },
            "猴车乘坐": {
                "regulation_id": "CSR-002",
                "title": "架空乘人装置（猴车）安全管理规定",
                "description": "煤矿猴车乘坐的安全要求和注意事项",
                "requirements": [
                    {
                        "id": "REQ-101",
                        "category": "乘坐规范",
                        "content": "乘坐时必须面向行进方向，双手紧握把手，严禁反向乘坐",
                        "severity": "high"
                    },
                    {
                        "id": "REQ-102",
                        "category": "物品携带",
                        "content": "严禁携带超长（>50cm）、超重物品乘坐猴车",
                        "severity": "critical"
                    },
                    {
                        "id": "REQ-103",
                        "category": "防护装备",
                        "content": "乘坐时必须佩戴安全帽",
                        "severity": "high"
                    },
                    {
                        "id": "REQ-104",
                        "category": "上下车",
                        "content": "上下车时要注意抓稳把手，不得抢上抢下",
                        "severity": "medium"
                    }
                ]
            },
            "动火作业": {
                "regulation_id": "CSR-003",
                "title": "煤矿动火作业安全管理规定",
                "description": "煤矿井下动火作业的安全要求和操作规范",
                "requirements": [
                    {
                        "id": "REQ-201",
                        "category": "作业审批",
                        "content": "必须办理动火作业票，明确动火等级和安全措施",
                        "severity": "critical"
                    },
                    {
                        "id": "REQ-202",
                        "category": "气体检测",
                        "content": "动火前必须检测瓦斯浓度，瓦斯浓度不超过0.5%",
                        "severity": "critical"
                    },
                    {
                        "id": "REQ-203",
                        "category": "隔离措施",
                        "content": "动火点周围8米内不得有可燃物，必要时设置防火隔离",
                        "severity": "high"
                    },
                    {
                        "id": "REQ-204",
                        "category": "监护人员",
                        "content": "动火期间必须有专人监护，配备灭火器材",
                        "severity": "critical"
                    }
                ]
            }
        }
    
    def _get_default_task_definitions(self) -> Dict[str, Any]:
        """获取默认任务定义"""
        return {
            "受限空间作业": {
                "task_id": "TASK-001",
                "task_name": "受限空间作业监控",
                "expected_duration": {
                    "min": 600,      # 最短10分钟
                    "typical": 1800, # 常规30分钟
                    "max": 3600      # 最长60分钟
                },
                "stages": [
                    {
                        "stage": "准备阶段",
                        "duration": "5-10分钟",
                        "key_actions": ["气体检测", "通风", "装备穿戴", "审批确认"]
                    },
                    {
                        "stage": "进入阶段",
                        "duration": "2-5分钟",
                        "key_actions": ["下梯", "安全绳固定", "通讯确认"]
                    },
                    {
                        "stage": "作业阶段",
                        "duration": "15-40分钟",
                        "key_actions": ["清理作业", "维修作业", "检查作业"]
                    },
                    {
                        "stage": "撤离阶段",
                        "duration": "2-5分钟",
                        "key_actions": ["上梯", "人数核对", "工具清点"]
                    }
                ],
                "checklist_template": [
                    {
                        "item": "是否办理作业票",
                        "type": "boolean",
                        "required": True,
                        "regulation_ref": "REQ-001"
                    },
                    {
                        "item": "是否进行气体检测",
                        "type": "boolean",
                        "required": True,
                        "regulation_ref": "REQ-002"
                    },
                    {
                        "item": "是否佩戴防护装备",
                        "type": "boolean",
                        "required": True,
                        "regulation_ref": "REQ-004"
                    },
                    {
                        "item": "是否设置监护人",
                        "type": "boolean",
                        "required": True,
                        "regulation_ref": "REQ-005"
                    },
                    {
                        "item": "是否准备应急设备",
                        "type": "boolean",
                        "required": True,
                        "regulation_ref": "REQ-006"
                    },
                    {
                        "item": "进入和离开人数是否一致",
                        "type": "boolean",
                        "required": True,
                        "regulation_ref": "REQ-007"
                    }
                ]
            },
            "猴车乘坐": {
                "task_id": "TASK-002",
                "task_name": "猴车乘坐安全监控",
                "expected_duration": {
                    "min": 10,      # 最短10秒
                    "typical": 30,  # 常规30秒
                    "max": 60       # 最长60秒
                },
                "stages": [
                    {
                        "stage": "接近阶段",
                        "duration": "2-5秒",
                        "key_actions": ["接近猴车", "准备上车"]
                    },
                    {
                        "stage": "上车阶段",
                        "duration": "2-3秒",
                        "key_actions": ["抓握把手", "站稳车厢"]
                    },
                    {
                        "stage": "乘坐阶段",
                        "duration": "5-50秒",
                        "key_actions": ["保持姿势", "握紧把手"]
                    },
                    {
                        "stage": "下车阶段",
                        "duration": "1-2秒",
                        "key_actions": ["准备下车", "安全离开"]
                    }
                ],
                "checklist_template": [
                    {
                        "item": "是否携带物品",
                        "type": "boolean",
                        "required": True,
                        "regulation_ref": "REQ-102"
                    },
                    {
                        "item": "物品尺寸是否超标（>50cm）",
                        "type": "boolean",
                        "required": True,
                        "regulation_ref": "REQ-102"
                    },
                    {
                        "item": "是否正确站立",
                        "type": "boolean",
                        "required": True,
                        "regulation_ref": "REQ-101"
                    },
                    {
                        "item": "是否佩戴安全帽",
                        "type": "boolean",
                        "required": True,
                        "regulation_ref": "REQ-103"
                    }
                ]
            }
        }
    
    def query_regulation(self, task_type: str) -> Optional[Dict[str, Any]]:
        """
        查询安全规范
        
        Args:
            task_type: 任务类型
            
        Returns:
            安全规范详情
        """
        regulation = self.regulations.get(task_type)
        if regulation:
            logger.debug(f"找到规范: {task_type} - {regulation['title']}")
        else:
            logger.warning(f"未找到规范: {task_type}")
        return regulation
    
    def query_task_definition(self, task_type: str) -> Optional[Dict[str, Any]]:
        """
        查询任务定义
        
        Args:
            task_type: 任务类型
            
        Returns:
            任务定义详情
        """
        task_def = self.task_definitions.get(task_type)
        if task_def:
            logger.debug(f"找到任务定义: {task_type} - {task_def['task_name']}")
        else:
            logger.warning(f"未找到任务定义: {task_type}")
        return task_def
    
    def get_checklist(self, task_type: str) -> List[Dict[str, Any]]:
        """
        获取任务的检查清单
        
        Args:
            task_type: 任务类型
            
        Returns:
            检查清单列表
        """
        task_def = self.query_task_definition(task_type)
        if not task_def:
            return []
        
        checklist = task_def.get("checklist_template", [])
        
        # 补充规范详情
        regulation = self.query_regulation(task_type)
        if regulation:
            for item in checklist:
                ref = item.get("regulation_ref")
                if ref:
                    # 查找对应的规范要求
                    for req in regulation.get("requirements", []):
                        if req["id"] == ref:
                            item["regulation_detail"] = req
                            break
        
        logger.debug(f"生成检查清单: {task_type}, {len(checklist)}项")
        return checklist
    
    def get_expected_duration(self, task_type: str) -> Optional[Dict[str, int]]:
        """
        获取任务预期时长
        
        Args:
            task_type: 任务类型
            
        Returns:
            预期时长字典 {min, typical, max}
        """
        task_def = self.query_task_definition(task_type)
        if not task_def:
            return None
        
        return task_def.get("expected_duration")
    
    def search_by_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """
        根据关键词搜索相关规范
        
        Args:
            keyword: 关键词
            
        Returns:
            匹配的规范列表
        """
        results = []
        keyword_lower = keyword.lower()
        
        for task_type, regulation in self.regulations.items():
            # 检查任务类型、标题、描述是否包含关键词
            if (keyword_lower in task_type.lower() or 
                keyword_lower in regulation.get("title", "").lower() or
                keyword_lower in regulation.get("description", "").lower()):
                results.append({
                    "task_type": task_type,
                    "regulation": regulation
                })
                continue
            
            # 检查具体要求是否包含关键词
            for req in regulation.get("requirements", []):
                if (keyword_lower in req.get("category", "").lower() or
                    keyword_lower in req.get("content", "").lower()):
                    results.append({
                        "task_type": task_type,
                        "regulation": regulation,
                        "matched_requirement": req
                    })
                    break
        
        logger.debug(f"关键词搜索: '{keyword}', 找到{len(results)}条相关规范")
        return results
    
    def get_all_task_types(self) -> List[str]:
        """
        获取所有任务类型
        
        Returns:
            任务类型列表
        """
        return list(self.task_definitions.keys())


