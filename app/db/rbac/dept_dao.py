from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from app.models.rbac import SysDept


class DeptDao:
    """部门数据访问对象"""

    @staticmethod
    def generate_dept_path(db: Session, parent_id: Optional[int]) -> str:
        """生成部门的 Materialized Path

        Args:
            db: 数据库会话
            parent_id: 父部门ID，None表示根部门

        Returns:
            str: 生成的路径，格式如 "/0/" 或 "/0/1/" 或 "/0/1/2/"
        """
        if parent_id is None:
            # 根部门
            return "/0/"

        parent = db.query(SysDept).filter(
            SysDept.id == parent_id,
            SysDept.is_deleted == False
        ).first()
        if not parent:
            raise ValueError(f"Parent department with id {parent_id} not found")

        # 确保父部门路径以 / 结尾
        parent_path = parent.path if parent.path.endswith('/') else f"{parent.path}/"
        return f"{parent_path}{parent.id}/"

    @staticmethod
    def calculate_dept_depth(path: str) -> int:
        """根据路径计算部门深度

        Args:
            path: Materialized Path，格式如 "/0/" 或 "/0/1/"

        Returns:
            int: 部门深度，根部门深度为0
        """
        # 去除首尾的 /，然后按 / 分割，计算节点数量
        path = path.strip('/')
        if not path:
            return 0
        return len(path.split('/')) - 1

    @staticmethod
    def create_dept(db: Session, dept_data: dict) -> SysDept:
        """创建部门，自动处理 Materialized Path

        Args:
            db: 数据库会话
            dept_data: 部门数据，包含 parent_id

        Returns:
            SysDept: 创建的部门对象
        """
        parent_id = dept_data.get('parent_id')

        # 生成路径
        path = DeptDao.generate_dept_path(db, parent_id)

        # 计算深度
        depth = DeptDao.calculate_dept_depth(path)

        # 创建部门对象
        dept = SysDept(
            **dept_data,
            path=path,
            depth=depth
        )

        db.add(dept)
        db.commit()
        db.refresh(dept)

        # 更新路径，将部门ID添加到路径中
        # 例如：根部门初始路径是 /0/，创建后更新为 /{dept.id}/
        if parent_id is None:
            dept.path = f"/{dept.id}/"
            dept.depth = 0
        else:
            # 子部门路径：父部门路径 + 部门ID + /
            parent = db.query(SysDept).filter(SysDept.id == parent_id).first()
            parent_path = parent.path if parent.path.endswith('/') else f"{parent.path}/"
            dept.path = f"{parent_path}{dept.id}/"
            dept.depth = parent.depth + 1

        db.commit()
        db.refresh(dept)

        return dept

    @staticmethod
    def get_dept_by_id(db: Session, dept_id: int) -> Optional[SysDept]:
        """根据ID获取部门"""
        return db.query(SysDept).filter(
            SysDept.id == dept_id,
            SysDept.is_deleted == False
        ).first()

    @staticmethod
    def get_all_depts(db: Session) -> List[SysDept]:
        """获取所有部门"""
        return db.query(SysDept).filter(
            SysDept.is_deleted == False
        ).order_by(SysDept.path, SysDept.sort_order).all()

    @staticmethod
    def get_dept_by_parent(db: Session, parent_id: Optional[int]) -> List[SysDept]:
        """获取指定父部门下的所有直接子部门"""
        return db.query(SysDept).filter(
            SysDept.parent_id == parent_id,
            SysDept.is_deleted == False
        ).order_by(SysDept.sort_order).all()

    @staticmethod
    def get_dept_subtree(db: Session, dept_id: int) -> List[SysDept]:
        """获取指定部门及其所有子部门（包括多级子部门）

        使用 Materialized Path 高效查询子树

        Args:
            db: 数据库会话
            dept_id: 部门ID

        Returns:
            List[SysDept]: 部门及其所有子部门列表
        """
        dept = db.query(SysDept).filter(
            SysDept.id == dept_id,
            SysDept.is_deleted == False
        ).first()
        if not dept:
            return []

        # 使用 like 查询所有路径以当前部门路径开头的部门
        # 例如：当前部门路径是 /1/，则查询所有路径 like "/1/%" 的部门
        return db.query(SysDept).filter(
            SysDept.path.like(f"{dept.path}%"),
            SysDept.status == "ACTIVE",
            SysDept.is_deleted == False
        ).order_by(SysDept.path, SysDept.sort_order).all()

    @staticmethod
    def update_dept(db: Session, dept_id: int, update_data: dict) -> Optional[SysDept]:
        """更新部门信息，支持更新父部门（会自动更新子部门路径）

        Args:
            db: 数据库会话
            dept_id: 部门ID
            update_data: 更新数据

        Returns:
            Optional[SysDept]: 更新后的部门对象，若不存在返回 None
        """
        dept = db.query(SysDept).filter(SysDept.id == dept_id).first()
        if not dept:
            return None

        old_parent_id = dept.parent_id
        new_parent_id = update_data.get('parent_id', old_parent_id)

        # 如果父部门发生变化，需要更新路径
        if new_parent_id != old_parent_id:
            # 获取当前部门及其所有子部门
            dept_with_children = DeptDao.get_dept_subtree(db, dept_id)

            # 生成新路径
            new_path = DeptDao.generate_dept_path(db, new_parent_id)
            new_depth = DeptDao.calculate_dept_depth(new_path)

            # 更新当前部门
            dept.parent_id = new_parent_id
            dept.path = f"{new_path}{dept.id}/"
            dept.depth = new_depth + 1

            # 更新所有子部门的路径和深度
            for child in dept_with_children:
                if child.id != dept_id:  # 跳过当前部门
                    # 计算子部门相对于当前部门的相对路径
                    relative_path = child.path.replace(dept.path, '', 1) if child.path.startswith(dept.path) else child.path
                    # 生成新路径
                    child.path = f"{dept.path}{relative_path}"
                    # 计算新深度
                    child.depth = dept.depth + DeptDao.calculate_dept_depth(relative_path)

        # 更新其他字段
        for key, value in update_data.items():
            if key != 'parent_id' and hasattr(dept, key):
                setattr(dept, key, value)

        db.commit()
        db.refresh(dept)
        return dept

    @staticmethod
    def delete_dept(db: Session, dept_id: int) -> bool:
        """删除部门

        Args:
            db: 数据库会话
            dept_id: 部门ID

        Returns:
            bool: 是否删除成功
        """
        dept = db.query(SysDept).filter(SysDept.id == dept_id).first()
        if not dept:
            return False

        # 检查是否有子部门
        has_children = db.query(SysDept).filter(
            SysDept.parent_id == dept_id,
            SysDept.is_deleted == False
        ).first() is not None
        if has_children:
            raise ValueError(f"Cannot delete department with id {dept_id} as it has children")

        dept.is_deleted = True
        db.commit()
        db.refresh(dept)
        return True

    @staticmethod
    def get_dept_tree(db: Session) -> List[Dict[str, Any]]:
        """获取部门树结构

        Returns:
            List[Dict[str, Any]]: 部门树，每个部门包含 children 字段
        """
        all_depts = DeptDao.get_all_depts(db)

        # 将部门转换为字典，并构建映射
        dept_map = {}
        for dept in all_depts:
            dept_dict = {
                "id": dept.id,
                "name": dept.name,
                "parentId": dept.parent_id,
                "path": dept.path,
                "depth": dept.depth,
                "sortOrder": dept.sort_order,
                "leaderId": dept.leader_id,
                "status": dept.status,
                "createTime": dept.create_time,
                "updateTime": dept.update_time,
                "createBy": dept.create_by,
                "updateBy": dept.update_by,
                "remark": dept.remark,
                "children": []
            }
            dept_map[dept.id] = dept_dict

        # 构建树结构
        root_depts = []
        for dept_id, dept_dict in dept_map.items():
            parent_id = dept_dict["parent_id"]
            if parent_id is None:
                # 根部门
                root_depts.append(dept_dict)
            else:
                # 子部门，添加到父部门的 children 中
                if parent_id in dept_map:
                    dept_map[parent_id]["children"].append(dept_dict)

        return root_depts