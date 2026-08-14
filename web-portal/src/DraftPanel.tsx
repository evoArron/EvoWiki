import { useCallback, useEffect, useState } from "react";
import { Button, Drawer, Form, Input, List, Popconfirm, Space, Tag } from "antd";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type Draft = { id: number; draft_path: string; status: string; error: string | null };
type Props = { open: boolean; onClose: () => void; projectId: string; token: string; onPublished: () => void };

export function DraftPanel({ open, onClose, projectId, token, onPublished }: Props) {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [selected, setSelected] = useState<Draft>();
  const [content, setContent] = useState("");
  const [targetPath, setTargetPath] = useState("");
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const load = useCallback(async () => {
    const response = await fetch(`${API}/api/projects/${projectId}/drafts`, { headers });
    if (response.ok) setDrafts(await response.json() as Draft[]);
  }, [projectId, token]);

  useEffect(() => { if (open) void load(); }, [load, open]);

  async function openDraft(draft: Draft) {
    const response = await fetch(`${API}/api/projects/${projectId}/drafts/${draft.id}`, { headers });
    if (!response.ok) return;
    const data = await response.json() as { content: string };
    setSelected(draft);
    setContent(data.content);
    setTargetPath(draft.draft_path.replace(`${projectId}/.drafts/`, ""));
  }

  async function save() {
    if (!selected) return;
    await fetch(`${API}/api/projects/${projectId}/drafts/${selected.id}`, { method: "PUT", headers, body: JSON.stringify({ content }) });
  }

  async function reject(draft: Draft) {
    await fetch(`${API}/api/projects/${projectId}/drafts/${draft.id}`, { method: "DELETE", headers });
    if (selected?.id === draft.id) setSelected(undefined);
    await load();
  }

  async function publish(overwrite: boolean) {
    if (!selected) return;
    const response = await fetch(`${API}/api/projects/${projectId}/drafts/${selected.id}/publish`, { method: "POST", headers, body: JSON.stringify({ target_path: targetPath, overwrite }) });
    if (response.ok) {
      setSelected(undefined);
      await load();
      onPublished();
    }
  }

  return <Drawer title="待核对草稿" width={720} open={open} onClose={onClose}>
    {selected ? <Form layout="vertical" autoComplete="off">
      <Form.Item label="草稿路径"><Input value={selected.draft_path} disabled /></Form.Item>
      <Form.Item label="Markdown"><Input.TextArea rows={16} value={content} onChange={(event) => setContent(event.target.value)} /></Form.Item>
      <Form.Item label="发布路径"><Input value={targetPath} onChange={(event) => setTargetPath(event.target.value)} /></Form.Item>
      <Space><Button type="primary" onClick={() => void save()}>保存修订</Button><Button onClick={() => void publish(false)}>发布</Button><Popconfirm title="覆盖现有文档？" onConfirm={() => void publish(true)}><Button type="link">确认覆盖发布</Button></Popconfirm><Button type="link" onClick={() => setSelected(undefined)}>返回列表</Button></Space>
    </Form> : <List dataSource={drafts} locale={{ emptyText: "暂无待核对草稿" }} renderItem={(draft) => <List.Item actions={[<Button key="open" type="link" onClick={() => void openDraft(draft)}>预览</Button>, <Popconfirm key="reject" title="拒绝此草稿？" onConfirm={() => void reject(draft)}><Button type="link" danger>拒绝</Button></Popconfirm>]}><List.Item.Meta title={draft.draft_path} description={<Tag>{draft.status}</Tag>} /></List.Item>} />}
  </Drawer>;
}
