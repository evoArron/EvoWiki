import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Avatar, Button, Drawer, Form, Input, Select, Space, Table, Tabs, Tag } from "antd";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const ROLE_OPTIONS = [
  { value: "viewer", label: "查看者" },
  { value: "editor", label: "编辑者" },
  { value: "project_admin", label: "项目管理员" },
];
const AUDIT_ACTIONS = ["member.created", "member.updated", "member.password_reset", "member.status_changed", "member.system_role_changed", "project.created", "project.updated", "project.owner_transferred", "project.archived", "project.restored", "project.permission_changed", "project.permission_revoked"];

type Member = { username: string; display_name: string; role: string; is_active: boolean };
type Project = { project_id: string; name: string; description: string; owner_username: string; status: string; role?: string | null };
type Permission = { username: string; display_name: string; role: string };
type Audit = { id: number; actor_username: string; action: string; object_type: string; object_id: string; created_at: string };
type MemberDrawer = "create" | "edit" | "password" | null;
type ProjectDrawer = "create" | "edit" | "owner" | "permissions" | null;

type Props = { open: boolean; onClose: () => void; token: string | null; isSystemAdmin: boolean; manageableProjects: Project[] };

function errorText(response: Response) {
  return response.json().then((body: { detail?: string }) => body.detail || "操作失败，请检查输入和权限").catch(() => "操作失败，请检查输入和权限");
}

export function ManagementCenter({ open, onClose, token, isSystemAdmin, manageableProjects }: Props) {
  const [members, setMembers] = useState<Member[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [auditAction, setAuditAction] = useState<string>();
  const [memberQuery, setMemberQuery] = useState("");
  const [memberStatus, setMemberStatus] = useState<string>();
  const [memberRole, setMemberRole] = useState<string>();
  const [projectQuery, setProjectQuery] = useState("");
  const [projectStatus, setProjectStatus] = useState<string>();
  const [memberDrawer, setMemberDrawer] = useState<MemberDrawer>(null);
  const [projectDrawer, setProjectDrawer] = useState<ProjectDrawer>(null);
  const [selectedMember, setSelectedMember] = useState<Member>();
  const [selectedProject, setSelectedProject] = useState<Project>();
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [error, setError] = useState<string>();
  const [memberForm] = Form.useForm();
  const [projectForm] = Form.useForm();
  const [ownerForm] = Form.useForm();
  const [permissionForm] = Form.useForm();

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, "Content-Type": "application/json" }), [token]);
  const load = useCallback(async () => {
    if (!token) return;
    if (!isSystemAdmin) {
      setProjects(manageableProjects);
      return;
    }
    const [memberResult, projectResult] = await Promise.all([
      fetch(`${API}/api/admin/members`, { headers }),
      fetch(`${API}/api/admin/projects`, { headers }),
    ]);
    if (memberResult.ok) setMembers(await memberResult.json() as Member[]);
    if (projectResult.ok) setProjects(await projectResult.json() as Project[]);
  }, [headers, isSystemAdmin, manageableProjects, token]);
  const loadAudit = useCallback(async (page = auditPage, action = auditAction) => {
    if (!token || !isSystemAdmin) return;
    const query = new URLSearchParams({ page: String(page), page_size: "20" });
    if (action) query.set("action", action);
    const response = await fetch(`${API}/api/admin/audit-logs?${query}`, { headers });
    if (response.ok) {
      const data = await response.json() as { items: Audit[]; total: number };
      setAudit(data.items);
      setAuditTotal(data.total);
    }
  }, [auditAction, auditPage, headers, isSystemAdmin, token]);
  const loadPermissions = useCallback(async (projectId: string) => {
    const response = await fetch(`${API}/api/admin/projects/${projectId}/permissions`, { headers });
    if (response.ok) setPermissions(await response.json() as Permission[]);
  }, [headers]);

  useEffect(() => { if (open) { void load(); void loadAudit(); } }, [load, loadAudit, open]);

  async function submit(path: string, method: string, body?: object) {
    setError(undefined);
    try {
      const response = await fetch(`${API}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
      if (!response.ok) {
        setError(await errorText(response));
        return false;
      }
      await Promise.all([load(), loadAudit()]);
      return true;
    } catch {
      setError("无法连接管理服务，请稍后重试");
      return false;
    }
  }

  const filteredMembers = members.filter((member) => {
    const text = `${member.username} ${member.display_name}`.toLowerCase();
    return (!memberQuery || text.includes(memberQuery.toLowerCase()))
      && (!memberStatus || String(member.is_active) === memberStatus)
      && (!memberRole || member.role === memberRole);
  });
  const filteredProjects = projects.filter((project) => {
    const text = `${project.project_id} ${project.name} ${project.owner_username}`.toLowerCase();
    return (!projectQuery || text.includes(projectQuery.toLowerCase())) && (!projectStatus || project.status === projectStatus);
  });

  function openMember(kind: MemberDrawer, member?: Member) {
    setError(undefined);
    setSelectedMember(member);
    memberForm.resetFields();
    setMemberDrawer(kind);
    if (kind === "edit" && member) memberForm.setFieldsValue({ display_name: member.display_name, role: member.role });
  }
  function openProject(kind: ProjectDrawer, project?: Project) {
    setError(undefined);
    setSelectedProject(project);
    projectForm.resetFields();
    ownerForm.resetFields();
    permissionForm.resetFields();
    setProjectDrawer(kind);
    setPermissions([]);
    if (kind === "edit" && project) projectForm.setFieldsValue({ name: project.name, description: project.description });
    if (kind === "owner" && project) ownerForm.setFieldsValue({ owner_username: project.owner_username });
    if (kind === "permissions" && project) void loadPermissions(project.project_id);
  }

  const membersTab = <>
    <Space wrap style={{ marginBottom: 12 }}>
      <Input aria-label="搜索成员" placeholder="搜索登录名或姓名" value={memberQuery} onChange={(event) => setMemberQuery(event.target.value)} />
      <Select aria-label="成员状态" allowClear placeholder="成员状态" style={{ width: 110 }} value={memberStatus} onChange={setMemberStatus} options={[{ value: "true", label: "启用" }, { value: "false", label: "停用" }]} />
      <Select aria-label="系统角色" allowClear placeholder="系统角色" style={{ width: 130 }} value={memberRole} onChange={setMemberRole} options={[{ value: "member", label: "普通成员" }, { value: "system_admin", label: "系统管理员" }]} />
      <Button type="primary" onClick={() => openMember("create")}>新增成员</Button>
    </Space>
    <Table size="small" rowKey="username" dataSource={filteredMembers} pagination={false} scroll={{ x: 760 }} columns={[
      { title: "成员", render: (_, item: Member) => <Space><Avatar size="small">{item.display_name.slice(0, 1)}</Avatar><span>{item.display_name}</span></Space> },
      { title: "登录名", dataIndex: "username" },
      { title: "系统角色", render: (_, item: Member) => item.role === "system_admin" ? <Tag color="blue">系统管理员</Tag> : "普通成员" },
      { title: "状态", render: (_, item: Member) => <Tag color={item.is_active ? "green" : "default"}>{item.is_active ? "启用" : "停用"}</Tag> },
      { title: "操作", render: (_, item: Member) => <Space wrap><Button size="small" onClick={() => openMember("edit", item)}>编辑</Button><Button size="small" onClick={() => openMember("password", item)}>重置密码</Button><Button size="small" onClick={() => void submit(`/api/admin/members/${item.username}/status`, "POST", { is_active: !item.is_active })}>{item.is_active ? "停用" : "启用"}</Button></Space> },
    ]} />
  </>;

  const projectsTab = <>
    <Space wrap style={{ marginBottom: 12 }}>
      <Input aria-label="搜索项目" placeholder="搜索项目、名称或负责人" value={projectQuery} onChange={(event) => setProjectQuery(event.target.value)} />
      <Select aria-label="项目状态" allowClear placeholder="项目状态" style={{ width: 110 }} value={projectStatus} onChange={setProjectStatus} options={[{ value: "active", label: "活动" }, { value: "archived", label: "已归档" }]} />
      {isSystemAdmin && <Button type="primary" onClick={() => openProject("create")}>新增项目</Button>}
    </Space>
    <Table size="small" rowKey="project_id" dataSource={filteredProjects} pagination={false} scroll={{ x: 860 }} columns={[
      { title: "名称", dataIndex: "name" }, { title: "标识", dataIndex: "project_id" }, { title: "负责人", dataIndex: "owner_username" },
      { title: "状态", render: (_, item: Project) => <Tag color={item.status === "active" ? "green" : "default"}>{item.status === "active" ? "活动" : "已归档"}</Tag> },
      { title: "操作", render: (_, item: Project) => <Space wrap>{item.status === "active" && <><Button size="small" onClick={() => openProject("edit", item)}>编辑</Button><Button size="small" onClick={() => openProject("owner", item)}>转移负责人</Button><Button size="small" onClick={() => openProject("permissions", item)}>权限</Button></>}{isSystemAdmin && <Button size="small" onClick={() => void submit(`/api/admin/projects/${item.project_id}/${item.status === "active" ? "archive" : "restore"}`, "POST")}>{item.status === "active" ? "归档" : "恢复"}</Button>}</Space> },
    ]} />
  </>;

  const auditTab = <>
    <Select aria-label="审计操作" allowClear placeholder="筛选操作" style={{ marginBottom: 12, width: 220 }} value={auditAction} onChange={(action) => { setAuditAction(action); setAuditPage(1); void loadAudit(1, action); }} options={AUDIT_ACTIONS.map((action) => ({ value: action, label: action }))} />
    <Table size="small" rowKey="id" dataSource={audit} scroll={{ x: 700 }} pagination={{ current: auditPage, pageSize: 20, total: auditTotal, showSizeChanger: false, onChange: (page) => { setAuditPage(page); void loadAudit(page); } }} columns={[
      { title: "时间", dataIndex: "created_at", render: (value: string) => new Date(value).toLocaleString("zh-CN") }, { title: "操作者", dataIndex: "actor_username" }, { title: "操作", dataIndex: "action" }, { title: "对象", render: (_, item: Audit) => `${item.object_type}: ${item.object_id}` },
    ]} />
  </>;

  return <Drawer title="管理中心" width="min(960px, 100vw)" open={open} onClose={onClose}>
    {error && <Alert type="error" showIcon message={error} closable onClose={() => setError(undefined)} style={{ marginBottom: 12 }} />}
    <Tabs items={isSystemAdmin ? [{ key: "members", label: "成员", children: membersTab }, { key: "projects", label: "项目", children: projectsTab }, { key: "audit", label: "审计日志", children: auditTab }] : [{ key: "projects", label: "项目", children: projectsTab }]} />

    <Drawer title={memberDrawer === "create" ? "新增成员" : memberDrawer === "password" ? "重置密码" : "编辑成员"} width={420} open={memberDrawer !== null} onClose={() => setMemberDrawer(null)}>
      {memberDrawer === "password" ? <Form form={memberForm} layout="vertical" onFinish={async (values) => { if (selectedMember && await submit(`/api/admin/members/${selectedMember.username}/reset-password`, "POST", values)) setMemberDrawer(null); }}><Form.Item label="新临时密码" name="password" rules={[{ required: true, message: "请输入临时密码" }]}><Input.Password /></Form.Item><Button htmlType="submit" type="primary">重置</Button></Form> : <Form form={memberForm} layout="vertical" onFinish={async (values) => {
        const created = memberDrawer === "create";
        const saved = created ? await submit("/api/admin/members", "POST", values) : selectedMember && await submit(`/api/admin/members/${selectedMember.username}`, "PATCH", { display_name: values.display_name });
        if (saved && !created && values.role !== selectedMember?.role && !(await submit(`/api/admin/members/${selectedMember!.username}/system-role`, "POST", { role: values.role }))) return;
        if (saved) setMemberDrawer(null);
      }}>
        {memberDrawer === "create" && <><Form.Item label="登录名" name="username" rules={[{ required: true, message: "请输入登录名" }]}><Input /></Form.Item><Form.Item label="临时密码" name="password" rules={[{ required: true, message: "请输入临时密码" }]}><Input.Password /></Form.Item></>}
        <Form.Item label="姓名" name="display_name" rules={[{ required: true, message: "请输入姓名" }]}><Input /></Form.Item>
        {memberDrawer === "edit" && <Form.Item label="系统角色" name="role" rules={[{ required: true }]}><Select options={[{ value: "member", label: "普通成员" }, { value: "system_admin", label: "系统管理员" }]} /></Form.Item>}
        <Button htmlType="submit" type="primary">保存</Button>
      </Form>}
    </Drawer>

    <Drawer title={projectDrawer === "create" ? "新增项目" : projectDrawer === "owner" ? "转移负责人" : projectDrawer === "permissions" ? "项目权限" : "编辑项目"} width={460} open={projectDrawer !== null} onClose={() => setProjectDrawer(null)}>
      {projectDrawer === "owner" ? <Form form={ownerForm} layout="vertical" onFinish={async (values) => { if (selectedProject && await submit(`/api/admin/projects/${selectedProject.project_id}/owner`, "POST", values)) setProjectDrawer(null); }}><Form.Item label="新负责人登录名" name="owner_username" rules={[{ required: true, message: "请输入负责人登录名" }]}><Input /></Form.Item><Button htmlType="submit" type="primary">转移</Button></Form> : projectDrawer === "permissions" ? <><Form form={permissionForm} layout="vertical" onFinish={async (values) => { if (selectedProject && await submit(`/api/admin/projects/${selectedProject.project_id}/permissions/${values.username}`, "PUT", { role: values.role })) { permissionForm.resetFields(); void loadPermissions(selectedProject.project_id); } }}><Space.Compact block><Form.Item name="username" rules={[{ required: true, message: "请输入成员登录名" }]} style={{ flex: 1, marginBottom: 12 }}><Input placeholder="成员登录名" /></Form.Item><Form.Item name="role" rules={[{ required: true, message: "请选择角色" }]} style={{ marginBottom: 12 }}><Select placeholder="角色" style={{ width: 130 }} options={ROLE_OPTIONS} /></Form.Item><Button htmlType="submit" type="primary">授权</Button></Space.Compact></Form><Table size="small" rowKey="username" dataSource={permissions} pagination={false} columns={[{ title: "成员", render: (_, item: Permission) => `${item.display_name} (${item.username})` }, { title: "角色", render: (_, item: Permission) => <Select aria-label={`${item.username} 的项目角色`} size="small" value={item.role} style={{ width: 130 }} options={ROLE_OPTIONS} onChange={async (role) => { if (selectedProject && await submit(`/api/admin/projects/${selectedProject.project_id}/permissions/${item.username}`, "PUT", { role })) void loadPermissions(selectedProject.project_id); }} /> }, { title: "操作", render: (_, item: Permission) => <Button danger size="small" onClick={async () => { if (selectedProject && await submit(`/api/admin/projects/${selectedProject.project_id}/permissions/${item.username}`, "DELETE")) void loadPermissions(selectedProject.project_id); }}>撤销</Button> }]} /></> : <Form form={projectForm} layout="vertical" onFinish={async (values) => { const saved = projectDrawer === "create" ? await submit("/api/admin/projects", "POST", values) : selectedProject && await submit(`/api/admin/projects/${selectedProject.project_id}`, "PATCH", values); if (saved) setProjectDrawer(null); }}>
        {projectDrawer === "create" && <><Form.Item label="项目标识" name="project_id" rules={[{ required: true, message: "请输入项目标识" }]}><Input /></Form.Item><Form.Item label="负责人登录名" name="owner_username" rules={[{ required: true, message: "请输入负责人登录名" }]}><Input /></Form.Item></>}
        <Form.Item label="名称" name="name" rules={[{ required: true, message: "请输入项目名称" }]}><Input /></Form.Item><Form.Item label="描述" name="description"><Input.TextArea rows={3} /></Form.Item><Button htmlType="submit" type="primary">保存</Button>
      </Form>}
    </Drawer>
  </Drawer>;
}
