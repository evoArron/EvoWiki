import { isValidElement, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Alert, Button, Card, Divider, Form, Input, List, Select, Spin, Tree, Typography } from "antd";
import type { DataNode } from "antd/es/tree";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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

type DocumentNode = {
  title: string;
  key: string;
  is_leaf: boolean;
};

type LoginResponse = {
  access_token: string;
};

type Document = {
  path: string;
  content: string;
};

export function MermaidDiagram({ chart }: { chart: string }) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const diagramId = useId().replace(/:/g, "");

  useEffect(() => {
    if (!open || !container.current) {
      return;
    }
    let cancelled = false;
    void import("mermaid")
      .then(({ default: mermaid }) => {
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
        return mermaid.render(diagramId, chart);
      })
      .then(({ svg, bindFunctions }) => {
        if (cancelled || !container.current) {
          return;
        }
        container.current.innerHTML = svg;
        bindFunctions?.(container.current);
      })
      .catch(() => {
        if (!cancelled && container.current) {
          container.current.textContent = "图表无法渲染";
        }
      });
    return () => {
      cancelled = true;
    };
  }, [chart, diagramId, open]);

  return (
    <details className="mermaid-details" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Mermaid</summary>
      {open && <div ref={container} />}
    </details>
  );
}

function MarkdownPre({ children }: { children?: ReactNode }) {
  if (isValidElement<{ className?: string; children?: ReactNode }>(children) && children.props.className === "language-mermaid") {
    return <MermaidDiagram chart={String(children.props.children).replace(/\n$/, "")} />;
  }
  return <pre>{children}</pre>;
}

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

function replaceChildren(nodes: DataNode[], key: string, children: DataNode[]): DataNode[] {
  return nodes.map((node) => {
    if (node.key === key) {
      return { ...node, children };
    }
    return node.children ? { ...node, children: replaceChildren(node.children, key, children) } : node;
  });
}

export function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [treeData, setTreeData] = useState<DataNode[]>([]);
  const [document, setDocument] = useState<Document | null>(null);
  const treeRequest = useRef(0);
  const documentRequest = useRef(0);
  const [loading, setLoading] = useState(true);
  const [documentLoading, setDocumentLoading] = useState(false);
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

  async function loadTree(projectId: string, path = "docs"): Promise<DataNode[]> {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) {
      return [];
    }
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/tree?path=${encodeURIComponent(path)}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      throw new ApiError(response.status);
    }
    const nodes = (await response.json()) as DocumentNode[];
    return nodes.map((node) => ({ title: node.title, key: node.key, isLeaf: node.is_leaf }));
  }

  async function selectProject(projectId: string) {
    const requestId = ++treeRequest.current;
    ++documentRequest.current;
    setError(null);
    setActiveProject(projectId);
    setDocument(null);
    setDocumentLoading(false);
    try {
      const nodes = await loadTree(projectId);
      if (requestId === treeRequest.current) {
        setTreeData(nodes);
      }
    } catch {
      if (requestId === treeRequest.current) {
        setError("无法读取项目文档树");
      }
    }
  }

  async function loadTreeChildren(node: DataNode) {
    if (!activeProject || node.isLeaf) {
      return;
    }
    try {
      const children = await loadTree(activeProject, String(node.key));
      setTreeData((current) => replaceChildren(current, String(node.key), children));
    } catch {
      setError("无法读取项目文档树");
    }
  }

  async function openDocument(path: string) {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token || !activeProject) {
      return;
    }
    const requestId = ++documentRequest.current;
    setError(null);
    setDocumentLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/projects/${activeProject}/documents?path=${encodeURIComponent(path)}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) {
        throw new ApiError(response.status);
      }
      const nextDocument = (await response.json()) as Document;
      if (requestId === documentRequest.current) {
        setDocument(nextDocument);
      }
    } catch {
      if (requestId === documentRequest.current) {
        setError("无法读取文档");
      }
    } finally {
      if (requestId === documentRequest.current) {
        setDocumentLoading(false);
      }
    }
  }

  function logout() {
    ++documentRequest.current;
    sessionStorage.removeItem(TOKEN_KEY);
    setActiveProject(null);
    setDocument(null);
    setProjects([]);
    setTreeData([]);
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
      <Card title="EvoWiki" className={activeProject ? "identity-card document-card" : "identity-card"}>
        <Typography.Paragraph>当前身份：{user.username}</Typography.Paragraph>
        <Typography.Paragraph>角色：{user.role}</Typography.Paragraph>
        <Button onClick={logout}>退出登录</Button>
        {error && <Alert className="login-error" type="error" showIcon message={error} />}

        <Divider>我的项目</Divider>
        <List
          dataSource={projects}
          locale={{ emptyText: "暂无授权项目" }}
          renderItem={(project) => (
            <List.Item actions={[<Button key={project.project_id} onClick={() => selectProject(project.project_id)}>浏览文档</Button>]}>
              {project.project_id}（{project.role}）
            </List.Item>
          )}
        />
        {activeProject && (
          <>
            <Tree
              className="document-tree"
              loadData={loadTreeChildren}
              onSelect={(_, info) => {
                if (info.node.isLeaf) {
                  void openDocument(String(info.node.key));
                }
              }}
              treeData={treeData}
            />
            {documentLoading && <Spin />}
            {document && (
              <article className="markdown-document">
                <Typography.Title level={2}>{document.path}</Typography.Title>
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ pre: MarkdownPre }}>
                  {document.content}
                </ReactMarkdown>
              </article>
            )}
          </>
        )}

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
