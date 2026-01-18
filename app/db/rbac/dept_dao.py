from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from app.models.rbac import SysDept
from app.utils.id_generator import generate_id


class DeptDao:
    """部门数据访问对象"""

    @staticmethod
    def check_circular_reference(db: Session, dept_id: int, new_parent_id: Optional[int]) -> bool:
        """检查是否存在循环引用

        Args:
            db: 数据库会话
            dept_id: 当前部门ID
            new_parent_id: 新的父部门ID

        Returns:
            bool: 如果存在循环引用返回True，否则返回False
        """
        if new_parent_id is None:
            # 根部门不会有循环引用
            return False

        if dept_id == new_parent_id:
            # 部门不能成为自己的父部门
            return True

        # 检查新父部门是否是当前部门的子部门（即，新父部门是否在当前部门的子树中）
        # 如果是，则会产生循环引用
        parent_dept = db.query(SysDept).filter(
            SysDept.id == new_parent_id,
            SysDept.is_deleted == False
        ).first()

        if not parent_dept:
            # 父部门不存在，这不是循环引用，而是其他错误
            return False

        # 检查当前部门是否在父部门的子树中
        # 使用路径判断：如果当前部门的路径以父部门的路径开头，则当前部门是父部门的子部门
        current_dept = db.query(SysDept).filter(
            SysDept.id == dept_id,
            SysDept.is_deleted == False
        ).first()

        if current_dept and parent_dept.path.startswith(current_dept.path) and current_dept.path != parent_dept.path:
            # 父部门的路径以当前部门的路径开头，说明父部门是当前部门的子部门
            # 这会导致循环引用
            return True

        return False

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

        # 生成 initial path (will be corrected after insertion)
        initial_path = "/0/" if parent_id is None else DeptDao.generate_dept_path(db, parent_id)

        # Calculate initial depth
        initial_depth = 0 if parent_id is None else DeptDao.calculate_dept_depth(initial_path)

        # 如果没有提供ID，则生成新的ID
        if 'id' not in dept_data:
            # 从tenant_id中提取数字ID用于ID生成器
            tenant_id = dept_data.get('tenant_id', 1000000000000001)  # 使用默认租户ID
            # 确保tenant_id是整数
            if not isinstance(tenant_id, int):
                raise ValueError(f"tenant_id must be an integer, got {type(tenant_id)}")

            # 生成新的部门ID
            dept_id = generate_id(tenant_id, "dept")  # tenant_id不再直接编码到ID中，但可用于其他用途

            # 验证生成的ID是否在合理范围内
            # MySQL BIGINT范围是 -9223372036854775808 到 9223372036854775807
            if dept_id > 9223372036854775807:
                raise ValueError(f"Generated ID {dept_id} exceeds BIGINT range")

            dept_data['id'] = dept_id

        # Check for circular reference before creating the department
        # Since we're creating a new department, we only need to check if the parent_id
        # is in the subtree of departments that would be created
        if parent_id is not None:
            # For a new department, we just need to make sure the parent isn't a child of the new department
            # But since the department doesn't exist yet, we only need to check if parent points to itself
            if parent_id == dept_data['id']:
                raise ValueError(f"Cannot set department as its own parent")

        # Create department object with initial values
        dept = SysDept(
            **dept_data,
            path=initial_path,
            depth=initial_depth
        )

        db.add(dept)
        db.commit()
        db.refresh(dept)

        # Now update the path with the correct department ID
        if parent_id is None:
            # Root department: path should be /{dept.id}/
            dept.path = f"/{dept.id}/"
            dept.depth = 0
        else:
            # Sub-department: get parent and construct correct path
            parent = db.query(SysDept).filter(
                SysDept.id == parent_id,
                SysDept.is_deleted == False
            ).first()
            if parent:
                parent_path = parent.path if parent.path.endswith('/') else f"{parent.path}/"
                dept.path = f"{parent_path}{dept.id}/"
                dept.depth = parent.depth + 1
            else:
                # Parent department not found, raise an error
                raise ValueError(f"Parent department with id {parent_id} not found")

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
    def get_dept_by_name(db: Session, name: str, tenant_id: int) -> Optional[SysDept]:
        """根据部门名称和租户ID获取部门"""
        return db.query(SysDept).filter(
            SysDept.name == name,
            SysDept.tenant_id == tenant_id,
            SysDept.is_deleted == False
        ).first()

    @staticmethod
    def get_all_depts(db: Session) -> List[SysDept]:
        """获取所有部门"""
        return db.query(SysDept).filter(
            SysDept.is_deleted == False
        ).order_by(SysDept.path, SysDept.sort_order).all()

    @staticmethod
    def get_all_active_depts(db: Session) -> List[SysDept]:
        """获取所有激活的部门"""
        return db.query(SysDept).filter(
            SysDept.is_deleted == False,
            SysDept.status == 0
        ).order_by(SysDept.path, SysDept.sort_order).all()

    @staticmethod
    def get_dept_by_parent(db: Session, parent_id: Optional[int]) -> List[SysDept]:
        """获取指定父部门下的所有直接子部门

        Args:
            db: 数据库会话
            parent_id: 父部门ID

        Returns:
            List[SysDept]: 部门列表
        """
        query = db.query(SysDept).filter(
            SysDept.parent_id == parent_id,
            SysDept.is_deleted == False,
            SysDept.status == 0  # 只返回激活的部门
        )

        return query.order_by(SysDept.sort_order).all()

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

        # 构建查询
        query = db.query(SysDept).filter(
            SysDept.path.like(f"{dept.path}%"),
            SysDept.is_deleted == False,
            SysDept.status == 0  # 只返回激活的部门
        )

        return query.order_by(SysDept.path, SysDept.sort_order).all()

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

        # 如果父部门发生变化，需要检查循环引用
        if new_parent_id != old_parent_id:
            # 检查是否会产生循环引用
            if DeptDao.check_circular_reference(db, dept_id, new_parent_id):
                raise ValueError(f"Updating department would result in a circular reference")

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
    def get_dept_tree(db: Session, tenant_id: Optional[int] = None, name: Optional[str] = None, status: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取部门树结构

        Args:
            db: 数据库会话
            tenant_id: 租户ID，为None时返回所有租户的部门树
            name: 部门名称（模糊查询）
            status: 状态过滤，为None时不过滤状态，否则按指定状态过滤

        Returns:
            List[Dict[str, Any]]: 部门树，每个部门包含 children 字段
        """
        # 构建查询
        query = db.query(SysDept).filter(
            SysDept.is_deleted == False
        )

        # 添加租户过滤
        if tenant_id:
            query = query.filter(SysDept.tenant_id == tenant_id)

        # 添加名称模糊查询
        if name:
            query = query.filter(SysDept.name.contains(name))

        # 添加状态过滤（可选）
        if status is not None:
            query = query.filter(SysDept.status == status)

        all_depts = query.all()

        # 将部门转换为字典，并构建映射
        dept_map = {}
        for dept in all_depts:
            dept_dict = {
                "id": dept.id,
                "name": dept.name,
                "parent_id": dept.parent_id,
                "path": dept.path,
                "depth": dept.depth,
                "sort_order": dept.sort_order ,
                "status": dept.status,
                "tenant_id": dept.tenant_id,
                "create_time": dept.create_time,
                "update_time": dept.update_time,
                "create_by": dept.create_by,
                "update_by": dept.update_by,
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

    @staticmethod
    def get_full_dept_tree(db: Session, tenant_id: Optional[int] = None, status: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取完整的部门树结构

        Args:
            db: 数据库会话
            tenant_id: 租户ID，为None时返回所有租户的部门树
            status: 状态过滤，为None时不过滤状态，否则按指定状态过滤

        Returns:
            List[Dict[str, Any]]: 完整的部门树，每个部门包含 children 字段
        """
        # 获取所有部门
        query = db.query(SysDept).filter(
            SysDept.is_deleted == False
        )

        if tenant_id:
            query = query.filter(SysDept.tenant_id == tenant_id)

        # 添加状态过滤（可选）
        if status is not None:
            query = query.filter(SysDept.status == status)

        all_depts = query.all()

        # 将部门转换为字典，并构建映射
        dept_map = {}
        for dept in all_depts:
            dept_dict = {
                "id": dept.id,
                "name": dept.name,
                "parent_id": dept.parent_id,
                "path": dept.path,
                "depth": dept.depth,
                "sort_order": dept.sort_order,
                "status": dept.status,
                "tenant_id": dept.tenant_id,
                "create_time": dept.create_time,
                "update_time": dept.update_time,
                "create_by": dept.create_by,
                "update_by": dept.update_by,
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

    @staticmethod
    def get_depts_by_tenant_and_parent(db: Session, tenant_id: int, parent_id: Optional[int], skip: int = 0, limit: int = 100) -> List[SysDept]:
        """根据租户和父部门ID获取部门列表

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            parent_id: 父部门ID，None表示根部门
            skip: 跳过的记录数
            limit: 限制返回的记录数

        Returns:
            List[SysDept]: 部门列表
        """
        query = db.query(SysDept).filter(
            SysDept.tenant_id == tenant_id,
            SysDept.is_deleted == False,
            SysDept.status == 0  # 只返回激活的部门
        )

        # 根据 parent_id 过滤
        if parent_id is None:
            # 获取根部门（parent_id 为 None）
            query = query.filter(SysDept.parent_id.is_(None))
        else:
            # 获取指定 parent_id 的子部门
            query = query.filter(SysDept.parent_id == parent_id)

        # 应用分页
        return query.order_by(SysDept.sort_order).offset(skip).limit(limit).all()

    @staticmethod
    def get_depts_by_filters(db: Session, tenant_id: int, name: str = None, parent_id: int = None, skip: int = 0, limit: int = 100) -> List[SysDept]:
        """根据多种条件获取部门列表

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            name: 部门名称（模糊查询）
            parent_id: 父部门ID
            skip: 跳过的记录数
            limit: 限制返回的记录数

        Returns:
            List[SysDept]: 部门列表
        """
        query = db.query(SysDept).filter(
            SysDept.tenant_id == tenant_id,
            SysDept.is_deleted == False,
            SysDept.status == 0  # 只返回激活的部门
        )

        # 部门名称模糊查询
        if name:
            query = query.filter(SysDept.name.contains(name))

        # 父部门过滤
        if parent_id is None:
            # 获取根部门（parent_id 为 None）
            query = query.filter(SysDept.parent_id.is_(None))
        else:
            # 获取指定 parent_id 的子部门
            query = query.filter(SysDept.parent_id == parent_id)

        # 应用分页
        return query.order_by(SysDept.sort_order).offset(skip).limit(limit).all()

    @staticmethod
    def get_depts_by_filters_with_sort(db: Session, tenant_id: int, name: str = None, parent_id: int = None,status:int=None, skip: int = 0, limit: int = 100) -> List[SysDept]:
        """根据多种条件获取部门列表，支持排序

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            name: 部门名称（模糊查询）
            parent_id: 父部门ID
            skip: 跳过的记录数
            limit: 限制返回的记录数

        Returns:
            List[SysDept]: 部门列表
        """
        query = db.query(SysDept).filter(
            SysDept.tenant_id == tenant_id,
            SysDept.is_deleted == False,
            SysDept.status == status  # 只返回激活的部门
        )

        # 部门名称模糊查询
        if name:
            query = query.filter(SysDept.name.contains(name))

        # 父部门过滤
        if parent_id is None:
            # 获取根部门（parent_id 为 None）
            query = query.filter(SysDept.parent_id.is_(None))
        else:
            # 获取指定 parent_id 的子部门
            query = query.filter(SysDept.parent_id == parent_id)


        query = query.order_by( SysDept.sort_order.asc())
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def get_dept_count_by_filters(db: Session, tenant_id: int, name: str = None,status:int=None) -> int:
        """根据多种条件获取部门数量

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            name: 部门名称（模糊查询）
            status: 状态

        Returns:
            int: 部门数量
        """
        query = db.query(SysDept).filter(
            and_(
                SysDept.tenant_id == tenant_id,
                SysDept.is_deleted == False,
                SysDept.status == status
            )
        )

        # 部门名称模糊查询
        if name:
            query = query.filter(SysDept.name.contains(name))

        return query.count()

    @staticmethod
    def get_dept_count_by_tenant(db: Session, tenant_id: int) -> int:
        """获取租户下的部门数量

        Args:
            db: 数据库会话
            tenant_id: 租户ID

        Returns:
            int: 部门数量
        """
        return db.query(SysDept).filter(
            and_(
                SysDept.tenant_id == tenant_id,
                SysDept.is_deleted == False,
                SysDept.status == 0  # 只计算激活的部门
            )
        ).count()