import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Drawer, Form, Input, List, Popconfirm, Space, Tag } from "antd";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type Draft = { id: number; draft_path: string; status: string; error: string | null };
type Props = { open: boolean; onClose: () => void; projectId: string; token: string; onPublished: () => void };

export function DraftPanel({ open, onClose, projectId, token, onPublished }: Props) {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [selected, setSelected] = useState<Draft>();
  const [creating, setCreating] = useState(false);
  const [content, setContent] = useState("");
  const [draftPath, setDraftPath] = useState("");
  const [targetPath, setTargetPath] = useState("");
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const load = useCallback(async () => {
    const response = await fetch(`${API}/api/projects/${projectId}/drafts`, { headers });
    if (response.ok) setDrafts(await response.json() as Draft[]);
  }, [projectId, token]);

  useEffect(() => { if (open) void load(); }, [load, open]);

  function closeEditor() { setSelected(undefined); setCreating(false); setContent(""); setDraftPath(""); }
  async function openDraft(draft: Draft) {
    if (draft.status === "failed") return;
    const response = await fetch(`${API}/api/projects/${projectId}/drafts/${draft.id}`, { headers });
    if (!response.ok) return;
    const data = await response.json() as { content: string };
    setSelected(draft); setContent(data.content); setDraftPath(draft.draft_path.replace(`${projectId}/.drafts/`, "")); setTargetPath(draft.draft_path.replace(`${projectId}/.drafts/`, ""));
  }
  async function create() {
    const response = await fetch(`${API}/api/projects/${projectId}/drafts`, { method: "POST", headers, body: JSON.stringify({ path: draftPath, content }) });
    if (response.ok) { await load(); closeEditor(); }
  }
  async function save() { if (selected) await fetch(`${API}/api/projects/${projectId}/drafts/${selected.id}`, { method: "PUT", headers, body: JSON.stringify({ content }) }); }
  async function reject(draft: Draft) { await fetch(`${API}/api/projects/${projectId}/drafts/${draft.id}`, { method: "DELETE", headers }); if (selected?.id === draft.id) closeEditor(); await load(); }
  async function publish(overwrite: boolean) {
    if (!selected) return;
    const response = await fetch(`${API}/api/projects/${projectId}/drafts/${selected.id}/publish`, { method: "POST", headers, body: JSON.stringify({ target_path: targetPath, overwrite }) });
    if (response.ok) { closeEditor(); await load(); onPublished(); }
  }
  async function retry(draft: Draft) { const response = await fetch(`${API}/api/projects/${projectId}/drafts/${draft.id}/retry`, { method: "POST", headers }); if (response.ok) { await load(); onPublished(); } }

  const editor = <Form layout="vertical" autoComplete="off">
    <Form.Item label="草稿路径"><Input value={draftPath} disabled={!!selected} onChange={(event) => setDraftPath(event.target.value)} /></Form.Item>
    <Form.Item label="Markdown"><div className="draft-editor"><Input.TextArea aria-label="Markdown 源码" rows={18} value={content} onChange={(event) => setContent(event.target.value)} /><article className="draft-preview"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown></article></div></Form.Item>
    {selected && <Form.Item label="发布路径"><Input value={targetPath} onChange={(event) => setTargetPath(event.target.value)} /></Form.Item>}
    <Space>{creating ? <Button type="primary" onClick={() => void create()}>创建草稿</Button> : <><Button type="primary" onClick={() => void save()}>保存修订</Button><Button onClick={() => void publish(false)}>发布</Button><Popconfirm title="覆盖现有文档？" onConfirm={() => void publish(true)}><Button type="link">确认覆盖发布</Button></Popconfirm></>}<Button type="link" onClick={closeEditor}>返回列表</Button></Space>
  </Form>;

  return <Drawer title="待核对草稿" width={720} open={open} onClose={onClose}>
    {creating || selected ? editor : <><Button type="primary" onClick={() => setCreating(true)} style={{ marginBottom: 12 }}>新建草稿</Button><List dataSource={drafts} locale={{ emptyText: "暂无待核对草稿" }} renderItem={(draft) => <List.Item actions={draft.status === "failed" ? [<Button key="retry" type="link" onClick={() => void retry(draft)}>重试发布</Button>] : [<Button key="open" type="link" onClick={() => void openDraft(draft)}>预览</Button>, <Popconfirm key="reject" title="拒绝此草稿？" onConfirm={() => void reject(draft)}><Button type="link" danger>拒绝</Button></Popconfirm>]}><List.Item.Meta title={draft.draft_path} description={<Space><Tag>{draft.status}</Tag>{draft.error && <Alert type="error" message={draft.error} showIcon />}</Space>} /></List.Item>} /></>}
  </Drawer>;
}
