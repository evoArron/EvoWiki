import { useEffect, useState } from "react";
import { Alert, Button, Card, Form, Input, Spin, Typography } from "antd";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "evowiki.access-token";

type CurrentUser = {
  username: string;
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

export function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }

    readCurrentUser(token)
      .then(setUser)
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
    } catch {
      setError("无法连接认证服务，请稍后重试");
    }
  }

  function logout() {
    sessionStorage.removeItem(TOKEN_KEY);
    setUser(null);
  }

  if (loading) {
    return <Spin className="page-spinner" size="large" />;
  }

  if (user) {
    return (
      <main className="identity-page">
        <Card title="EvoWiki" className="identity-card">
          <Typography.Paragraph>当前身份：{user.username}</Typography.Paragraph>
          <Typography.Paragraph>角色：{user.role}</Typography.Paragraph>
          <Button onClick={logout}>退出登录</Button>
        </Card>
      </main>
    );
  }

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
