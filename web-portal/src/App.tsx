import { useEffect, useState } from "react";
import { Alert, Button, Card, Divider, Form, Input, List, Select, Spin, Typography } from "antd";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "evowiki.access-token";

type CurrentUser = {
  username: string;
  role: string;
};

type Project = {
  project_id: string;
  role: string;
};

type LoginResponse = {
  access_token: string;
};

class ApiError extends Error {
  constructor(readonly status: number) {
    super("认证请求失败");
  }
}

async function readCurrentUser(token: string): Promise<CurrentUser> {
  const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new ApiError(response.status);
  }
  return response.json() as Promise<CurrentUser>;
}

async function readProjects(token: string): Promise<Project[]> {
  const response = await fetch(`${API_BASE_URL}/api/projects`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new ApiError(response.status);
  }
  return response.json() as Promise<Project[]>;
}

export function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }

    readCurrentUser(token)
      .then(async (currentUser) => {
        setUser(currentUser);
        setProjects(await readProjects(token));
      })
      .catch((caught: unknown) => {
        if (caught instanceof ApiError && caught.status === 401) {
          sessionStorage.removeItem(TOKEN_KEY);
          return;
        }
        setError("无法连接认证服务，请稍后重试");
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(values: { username: string; password: string }) {
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      if (!response.ok) {
        setError("用户名或密码错误");
        return;
      }

      const { access_token } = (await response.json()) as LoginResponse;
      const currentUser = await readCurrentUser(access_token);
      sessionStorage.setItem(TOKEN_KEY, access_token);
      setUser(currentUser);
      setProjects(await readProjects(access_token));
    } catch {
      setError("无法连接认证服务，请稍后重试");
    }
  }

  async function adminRequest(path: string, body: object) {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) {
      return;
    }
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}${path}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        setError("操作失败，请检查输入和权限");
        return;
      }
      setProjects(await readProjects(token));
    } catch {
      setError("无法连接认证服务，请稍后重试");
    }
  }

  function logout() {
    sessionStorage.removeItem(TOKEN_KEY);
    setProjects([]);
    setUser(null);
  }

  if (loading) {
    return <Spin className="page-spinner" size="large" />;
  }

  if (!user) {
    return (
      <main className="identity-page">
        <Card title="登录 EvoWiki" className="identity-card">
          <Form layout="vertical" onFinish={login} requiredMark={false}>
            <Form.Item label="用户名" name="username" rules={[{ required: true, message: "请输入用户名" }]}>
              <Input autoComplete="username" />
            </Form.Item>
            <Form.Item label="密码" name="password" rules={[{ required: true, message: "请输入密码" }]}>
              <Input.Password autoComplete="current-password" />
            </Form.Item>
            {error && <Alert className="login-error" type="error" showIcon message={error} />}
            <Button htmlType="submit" type="primary" block>
              登录
            </Button>
          </Form>
        </Card>
      </main>
    );
  }

  return (
    <main className="identity-page">
      <Card title="EvoWiki" className="identity-card">
        <Typography.Paragraph>当前身份：{user.username}</Typography.Paragraph>
        <Typography.Paragraph>角色：{user.role}</Typography.Paragraph>
        <Button onClick={logout}>退出登录</Button>
        {error && <Alert className="login-error" type="error" showIcon message={error} />}

        <Divider>我的项目</Divider>
        <List
          dataSource={projects}
          locale={{ emptyText: "暂无授权项目" }}
          renderItem={(project) => <List.Item>{project.project_id}（{project.role}）</List.Item>}
        />

        {user.role === "admin" && (
          <>
            <Divider>管理员操作</Divider>
            <Form layout="vertical" onFinish={(values) => adminRequest("/api/admin/users", values)}>
              <Form.Item label="新成员用户名" name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                <Input />
              </Form.Item>
              <Form.Item label="新成员密码" name="password" rules={[{ required: true, message: "请输入密码" }]}>
                <Input.Password />
              </Form.Item>
              <Button htmlType="submit">创建成员</Button>
            </Form>
            <Form layout="vertical" onFinish={(values) => adminRequest("/api/admin/projects", values)}>
              <Form.Item label="新项目标识" name="project_id" rules={[{ required: true, message: "请输入项目标识" }]}>
                <Input placeholder="例如 alpha-project" />
              </Form.Item>
              <Button htmlType="submit">创建项目</Button>
            </Form>
            <Form
              layout="vertical"
              onFinish={(values) => adminRequest(`/api/admin/projects/${values.project_id}/permissions`, values)}
            >
              <Form.Item label="项目标识" name="project_id" rules={[{ required: true, message: "请输入项目标识" }]}>
                <Input />
              </Form.Item>
              <Form.Item label="成员用户名" name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                <Input />
              </Form.Item>
              <Form.Item label="项目角色" name="role" rules={[{ required: true, message: "请选择项目角色" }]}>
                <Select options={[{ value: "viewer", label: "查看者" }, { value: "editor", label: "编辑者" }]} />
              </Form.Item>
              <Button htmlType="submit">授予项目权限</Button>
            </Form>
          </>
        )}
      </Card>
    </main>
  );
}
