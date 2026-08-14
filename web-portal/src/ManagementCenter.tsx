import { useEffect, useState } from "react";
import { Button, Drawer, Form, Input, Space, Table, Tabs, Tag } from "antd";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
type Member = { username: string; display_name: string; role: string; is_active: boolean };
type Project = { project_id: string; name: string; description: string; owner_username: string; status: string };
type Audit = { id: number; actor_username: string; action: string; object_type: string; object_id: string; created_at: string };

export function ManagementCenter({ open, onClose, token }: { open: boolean; onClose: () => void; token: string | null }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [memberDrawer, setMemberDrawer] = useState(false);
  const [projectDrawer, setProjectDrawer] = useState(false);
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const load = async () => {
    if (!token) return;
    const [memberResult, projectResult, auditResult] = await Promise.all([
      fetch(`${API}/api/admin/members`, { headers }), fetch(`${API}/api/admin/projects`, { headers }), fetch(`${API}/api/admin/audit-logs`, { headers }),
    ]);
    if (memberResult.ok) setMembers(await memberResult.json());
    if (projectResult.ok) setProjects(await projectResult.json());
    if (auditResult.ok) setAudit((await auditResult.json()).items);
  };
  useEffect(() => { if (open) void load(); }, [open, token]);
  const request = async (path: string, method: string, body?: object) => { await fetch(`${API}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined }); await load(); };
  return <Drawer title="管理中心" width={960} open={open} onClose={onClose}>
    <Tabs items={[
      { key: "members", label: "成员", children: <><Button type="primary" onClick={() => setMemberDrawer(true)}>新增成员</Button><Table rowKey="username" dataSource={members} pagination={false} columns={[
        { title: "姓名", dataIndex: "display_name" }, { title: "登录名", dataIndex: "username" }, { title: "系统角色", dataIndex: "role" },
        { title: "状态", render: (_, item: Member) => <Tag color={item.is_active ? "green" : "default"}>{item.is_active ? "启用" : "停用"}</Tag> },
        { title: "操作", render: (_, item: Member) => <Button size="small" onClick={() => void request(`/api/admin/members/${item.username}/status`, "POST", { is_active: !item.is_active })}>{item.is_active ? "停用" : "启用"}</Button> },
      ]}/></> },
      { key: "projects", label: "项目", children: <><Button type="primary" onClick={() => setProjectDrawer(true)}>新增项目</Button><Table rowKey="project_id" dataSource={projects} pagination={false} columns={[
        { title: "名称", dataIndex: "name" }, { title: "标识", dataIndex: "project_id" }, { title: "负责人", dataIndex: "owner_username" },
        { title: "状态", dataIndex: "status" }, { title: "操作", render: (_, item: Project) => <Button size="small" onClick={() => void request(`/api/admin/projects/${item.project_id}/${item.status === "active" ? "archive" : "restore"}`, "POST")}>{item.status === "active" ? "归档" : "恢复"}</Button> },
      ]}/></> },
      { key: "audit", label: "审计日志", children: <Table rowKey="id" dataSource={audit} pagination={{ pageSize: 20 }} columns={[{ title: "时间", dataIndex: "created_at" }, { title: "操作者", dataIndex: "actor_username" }, { title: "操作", dataIndex: "action" }, { title: "对象", render: (_, item: Audit) => `${item.object_type}: ${item.object_id}` }]} /> },
    ]}/>
    <Drawer title="新增成员" width={420} open={memberDrawer} onClose={() => setMemberDrawer(false)}><Form layout="vertical" onFinish={async value => { await request("/api/admin/members", "POST", value); setMemberDrawer(false); }}><Form.Item label="登录名" name="username" rules={[{ required: true }]}><Input /></Form.Item><Form.Item label="姓名" name="display_name" rules={[{ required: true }]}><Input /></Form.Item><Form.Item label="临时密码" name="password" rules={[{ required: true }]}><Input.Password /></Form.Item><Button htmlType="submit" type="primary">创建</Button></Form></Drawer>
    <Drawer title="新增项目" width={420} open={projectDrawer} onClose={() => setProjectDrawer(false)}><Form layout="vertical" onFinish={async value => { await request("/api/admin/projects", "POST", value); setProjectDrawer(false); }}><Form.Item label="项目标识" name="project_id" rules={[{ required: true }]}><Input /></Form.Item><Form.Item label="名称" name="name" rules={[{ required: true }]}><Input /></Form.Item><Form.Item label="负责人登录名" name="owner_username" rules={[{ required: true }]}><Input /></Form.Item><Form.Item label="描述" name="description"><Input.TextArea /></Form.Item><Space><Button htmlType="submit" type="primary">创建</Button></Space></Form></Drawer>
  </Drawer>;
}
