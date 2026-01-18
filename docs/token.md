token 外部携带请求参数如下：


```json
{
  "loginType": "xxx",
  "loginId": "xxx",
  "rnStr":"02bb9cfe8d7844ecae8dbe62b1ba971a",
  "clientid": "02bb9cfe8d7844ecae8dbe62b1ba971a",
  "tenantId": "xxx",
  "userId": "xxx",
  "userName": "xxx",
  "deptId": "xxx",
  "deptName": "xxx",
  "deptCategory": "xxx"
}
```

-  根据请求中的 tenantId 有无已经注册好的租户
    - 存在： 开始检查部门
    - 不存在： 创建该租户。
-  部门检查。 根据请求中的 deptId 检查有无部门
    - 存在： 开始检查角色
    - 不存在： 穿件该部门，使用 deptName deptId tenantId
- 角色检查。 根据请求中的 tenantId + ROLE_ACCESS这个 code 检查有无角色
    - 存在： 根据这个角色，通过关联关系 获取所有的权限
        - 无权限： 查询 租户为 0 的 ROLE_ACCESS 对应的权限，复制一份权限。
        - 有权限： 获取权限。
    - 不存在： 创建该角色，使用 ROLE_ACCESS tenantId
        - 创建角色成功后，查询 租户为 0 的 ROLE_ACCESS 对应的权限，复制一份权限。
- 用户检查。 根据请求中的 tenantId + userId这个 code 检查有无用户
    - 存在： 获取用户。
    - 不存在： 创建该用户，使用 userId tenantId userName
        - 创建用户成功后，将用户角色关联起来。
        - 创建用户成功后，将用户部门关联起来。
- 更新到用户态中，用户态即有，permission_code，method，api_path， tenant_id, dept_id, role_id, user_id，user_name等。
- 鉴权，判断请求拦截是否在权限列表中
    - 在： 放行
    - 不在
        - 判断这个链接是否在 租户为 0 的 ROLE_ACCESS 对应的权限的中
            - 在： 更新当前租户的 ROLE_ACCESS 对应的权限。
            - 不在： 拒绝。403 错误。



## 超管的账号
eyJ1c2VySWQiOiAiMCIsICJ1c2VyTmFtZSI6ICJzdXBlcmFkbWluIiwgInRlbmFudElkIjogIjAiLCAidGVuYW50TmFtZSI6ICLns7vnu5/np5/miLciLCAiY29tcGFueU5hbWUiOiAi57O757uf5YWs5Y+4IiwgImNvbXBhbnlDb2RlIjogIkNPTVAtMCIsICJkZXB0SWQiOiAiMCIsICJkZXB0TmFtZSI6ICLns7vnu5/nrqHnkIbpg6giLCAiY2xpZW50aWQiOiAiMDJiYjljZmU4ZDc4NDRlY2FlOGRiZTYyYjFiYTk3MWEifQ==

## 普通用户的账号
