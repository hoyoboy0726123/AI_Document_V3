import React, { useEffect, useState } from "react";
import { Button, Card, Descriptions, Space, Tag, message, Modal, Input, Tabs, Table, Typography, Statistic, Row, Col, Tooltip, Badge, Popconfirm, Slider } from "antd";
import { FilePdfOutlined, ExclamationCircleOutlined, EditOutlined, DeleteOutlined, BookOutlined, PlusOutlined, DatabaseOutlined, ReloadOutlined, MergeCellsOutlined, ScissorOutlined } from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import apiClient from "../../services/api";
import PdfPreviewModal from "./PdfPreviewModal";
import "./DocumentDetail.css";

const DocumentDetail = ({ documentId, initialPage, initialHighlightKeyword, onBack, onEdit }) => {
  const [document, setDocument] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pdfPreviewVisible, setPdfPreviewVisible] = useState(false);
  const [notes, setNotes] = useState([]);
  const [editingNote, setEditingNote] = useState(null);
  const [isEditNoteModalVisible, setIsEditNoteModalVisible] = useState(false);
  const [editNoteForm, setEditNoteForm] = useState({ question: "", answer: "" });

  const [isCreateNoteModalVisible, setIsCreateNoteModalVisible] = useState(false);
  const [createNoteForm, setCreateNoteForm] = useState({ question: "", answer: "" });

  // 重新向量化狀態
  const [reVectorizing, setReVectorizing] = useState(false);

  // 向量塊管理狀態
  const [chunks, setChunks] = useState(null); // null = 未載入
  const [chunksLoading, setChunksLoading] = useState(false);
  const [editingChunk, setEditingChunk] = useState(null);
  const [editChunkText, setEditChunkText] = useState("");
  const [chunkSaving, setChunkSaving] = useState(false);
  const [addChunkVisible, setAddChunkVisible] = useState(false);
  const [newChunk, setNewChunk] = useState({ page: "", text: "" });
  const [addingChunk, setAddingChunk] = useState(false);
  const [expandedChunkId, setExpandedChunkId] = useState(null);
  const [selectedChunkIds, setSelectedChunkIds] = useState([]);
  const [merging, setMerging] = useState(false);
  const [splittingChunk, setSplittingChunk] = useState(null);
  const [splitAt, setSplitAt] = useState(0);
  const [splitting, setSplitting] = useState(false);

  const fetchDocument = async () => {
    if (!documentId) return;
    try {
      setLoading(true);
      const [docResp, notesResp] = await Promise.all([
        apiClient.get(`documents/${documentId}`),
        apiClient.get(`documents/${documentId}/notes`)
      ]);
      setDocument(docResp.data);
      setNotes(notesResp.data);
    } catch (error) {
      message.error(error.response?.data?.detail ?? "載入文件失敗");
    } finally {
      setLoading(false);
    }
  };

  const fetchNotes = async () => {
    try {
      const resp = await apiClient.get(`documents/${documentId}/notes`);
      setNotes(resp.data);
    } catch (error) {
      console.error("Fetch notes failed", error);
    }
  };

  const handleDeleteNote = async (noteId) => {
    Modal.confirm({
      title: '刪除筆記',
      content: '確定要刪除這則筆記嗎？',
      okText: '刪除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await apiClient.delete(`documents/${documentId}/notes/${noteId}`);
          message.success('筆記已刪除');
          fetchNotes();
        } catch (error) {
          message.error('刪除失敗');
        }
      },
    });
  };

  const openEditNoteModal = (note) => {
    setEditingNote(note);
    setEditNoteForm({ question: note.question, answer: note.answer });
    setIsEditNoteModalVisible(true);
  };

  const handleUpdateNote = async () => {
    try {
      await apiClient.put(`documents/${documentId}/notes/${editingNote.id}`, editNoteForm);
      message.success('筆記已更新');
      setIsEditNoteModalVisible(false);
      fetchNotes();
    } catch (error) {
      message.error('更新失敗');
    }
  };

  const handleCreateNote = async () => {
    if (!createNoteForm.question.trim() || !createNoteForm.answer.trim()) {
      message.warning("請填寫問題與內容");
      return;
    }
    try {
      await apiClient.post(`documents/${documentId}/notes`, createNoteForm);
      message.success('筆記已建立');
      setIsCreateNoteModalVisible(false);
      setCreateNoteForm({ question: "", answer: "" });
      fetchNotes();
    } catch (error) {
      message.error('建立失敗');
    }
  };

  const getRandomEmoji = (id) => {
    const emojis = ['📓', '💡', '🧠', '⚙️', '💻', '📚', '📝', '🎨', '🚀', '🧩'];
    let hash = 0;
    for (let i = 0; i < id.length; i++) {
      hash = id.charCodeAt(i) + ((hash << 5) - hash);
    }
    return emojis[Math.abs(hash) % emojis.length];
  };

  const NOTE_COLORS = [
    '#FFF7E0', // Light Yellow
    '#E3F2FD', // Light Blue
    '#F3E5F5', // Light Purple
    '#E0F2F1', // Light Teal
    '#FBE9E7', // Light Orange
    '#FCE4EC', // Light Pink
    '#E8EAF6', // Light Indigo
    '#F1F8E9', // Light Green
  ];

  useEffect(() => {
    fetchDocument();
  }, [documentId]);

  // 如果有初始頁面參數（來自搜尋結果），自動開啟 PDF 預覽
  useEffect(() => {
    if (document && initialPage) {
      setPdfPreviewVisible(true);
    }
  }, [document, initialPage]);


  const handleReVectorize = () => {
    if (!documentId) {
      return;
    }

    Modal.confirm({
      title: '重新向量化',
      icon: <ExclamationCircleOutlined />,
      content: '將重新計算此文件的向量索引，建議僅在內容變更後執行。',
      okText: '確認',
      cancelText: '取消',
      onOk: async () => {
        try {
          setReVectorizing(true);
          await apiClient.post(`documents/${documentId}/re-vectorize`);
          message.success('已重新向量化文件');
          await fetchDocument();
        } catch (error) {
          message.error(error.response?.data?.detail ?? '重新向量化失敗');
        } finally {
          setReVectorizing(false);
        }
      },
    });
  };

  // ── 向量塊操作 ────────────────────────────────────────────────────────────
  const fetchChunks = async () => {
    if (!documentId) return;
    try {
      setChunksLoading(true);
      const resp = await apiClient.get(`documents/${documentId}/chunks`);
      setChunks(resp.data);
    } catch (error) {
      message.error("載入向量塊失敗");
    } finally {
      setChunksLoading(false);
    }
  };

  const handleSaveChunk = async () => {
    if (!editingChunk || !editChunkText.trim()) return;
    try {
      setChunkSaving(true);
      await apiClient.put(`documents/${documentId}/chunks/${editingChunk.id}`, { text: editChunkText });
      message.success("向量塊已更新並重新向量化");
      setEditingChunk(null);
      fetchChunks();
    } catch (error) {
      message.error(error.response?.data?.detail ?? "更新失敗");
    } finally {
      setChunkSaving(false);
    }
  };

  const handleDeleteChunk = async (chunkId) => {
    try {
      await apiClient.delete(`documents/${documentId}/chunks/${chunkId}`);
      message.success("向量塊已刪除");
      fetchChunks();
    } catch (error) {
      message.error("刪除失敗");
    }
  };

  const handleAddChunk = async () => {
    if (!newChunk.text.trim()) { message.warning("請輸入文字內容"); return; }
    try {
      setAddingChunk(true);
      await apiClient.post(`documents/${documentId}/chunks`, {
        page: newChunk.page ? parseInt(newChunk.page) : null,
        text: newChunk.text,
      });
      message.success("向量塊已新增並向量化");
      setAddChunkVisible(false);
      setNewChunk({ page: "", text: "" });
      fetchChunks();
    } catch (error) {
      message.error(error.response?.data?.detail ?? "新增失敗");
    } finally {
      setAddingChunk(false);
    }
  };

  const handleMergeChunks = async () => {
    if (selectedChunkIds.length < 2) { message.warning("請至少選取 2 個向量塊"); return; }
    try {
      setMerging(true);
      await apiClient.post(`documents/${documentId}/chunks/merge`, { chunk_ids: selectedChunkIds });
      message.success("已合併並重新向量化");
      setSelectedChunkIds([]);
      fetchChunks();
    } catch (error) {
      message.error(error.response?.data?.detail ?? "合併失敗");
    } finally {
      setMerging(false);
    }
  };

  const handleSplitChunk = async () => {
    if (!splittingChunk || splitAt <= 0 || splitAt >= splittingChunk.text.length) {
      message.warning("請選擇有效的分割位置");
      return;
    }
    try {
      setSplitting(true);
      await apiClient.post(`documents/${documentId}/chunks/${splittingChunk.id}/split`, { split_at: splitAt });
      message.success("已分割並重新向量化");
      setSplittingChunk(null);
      fetchChunks();
    } catch (error) {
      message.error(error.response?.data?.detail ?? "分割失敗");
    } finally {
      setSplitting(false);
    }
  };

  const scoreColor = (score) => {
    if (score >= 0.8) return "#52c41a";
    if (score >= 0.5) return "#faad14";
    return "#ff4d4f";
  };

  const metadataEntries = document ? Object.entries(document.metadata ?? {}) : [];

  return (
    <Card
      loading={loading}
      title="文件詳情"
      extra={
        <Space>
          <Button
            onClick={handleReVectorize}
            disabled={!document || reVectorizing}
            loading={reVectorizing}
            type="default"
          >
            重新向量化
          </Button>
          <Button onClick={() => onEdit?.(document)} disabled={!document}>
            編輯
          </Button>
          <Button onClick={onBack}>返回列表</Button>
        </Space>
      }
    >
      {document && (
        <>
        <Tabs
          defaultActiveKey="info"
          onChange={(key) => { if (key === "chunks" && !chunks) fetchChunks(); }}
          items={[
            {
              key: "info",
              label: "文件資訊",
              children: (
                <>
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label="標題">{document.title}</Descriptions.Item>
            <Descriptions.Item label="PDF 文件">
              {document.pdf_path ? (
                <Button
                  type="primary"
                  icon={<FilePdfOutlined />}
                  onClick={() => setPdfPreviewVisible(true)}
                >
                  開啟 PDF 預覽
                </Button>
              ) : (
                <span style={{ color: "#999" }}>尚未上傳 PDF</span>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="分類結果">
              {document.classification ? (
                <Tag color="green">{document.classification.name}</Tag>
              ) : (
                <Tag>尚未分類</Tag>
              )}
            </Descriptions.Item>
            {metadataEntries.map(([key, value]) => (
              <Descriptions.Item label={key} key={key}>
                {Array.isArray(value) ? (
                  <Space wrap>
                    {value.map((item) => (
                      <Tag key={item}>{item}</Tag>
                    ))}
                  </Space>
                ) : (
                  value ?? "-"
                )}
              </Descriptions.Item>
            ))}
          </Descriptions>

          {/* Notes Section */}
          <div style={{ marginTop: 32 }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
              <BookOutlined style={{ fontSize: 24, marginRight: 8, color: '#5f6368' }} />
              <span style={{ fontSize: 22, fontWeight: 400, color: '#202124' }}>我的筆記本 ({notes.length})</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 20 }}>
              {/* Create New Note Card */}
              <div
                onClick={() => setIsCreateNoteModalVisible(true)}
                style={{
                  height: '240px',
                  backgroundColor: '#fff',
                  borderRadius: 16,
                  border: '1px solid #e0e0e0',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  boxShadow: '0 2px 4px rgba(0,0,0,0.02)'
                }}
                className="create-note-card"
              >
                <div style={{
                  width: 48, height: 48, borderRadius: '50%',
                  background: '#E8F0FE', color: '#1967D2',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 12, fontSize: 24
                }}>
                  <PlusOutlined />
                </div>
                <div style={{ fontSize: 16, fontWeight: 500, color: '#3c4043' }}>建立新的筆記</div>
              </div>

              {/* Existing Notes */}
              {notes.map((note, index) => {
                const bgColor = NOTE_COLORS[index % NOTE_COLORS.length];
                const emoji = getRandomEmoji(note.id);

                return (
                  <Card
                    key={note.id}
                    size="small"
                    bordered={false}
                    title={
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingBottom: 4 }}>
                        <div style={{ fontSize: 24 }}>{emoji}</div>
                        <div style={{
                          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                          fontSize: 16, fontWeight: 700, color: '#202124', flex: 1
                        }} title={note.question}>
                          {note.question}
                        </div>
                      </div>
                    }
                    extra={
                      <Space size={0}>
                        <Button type="text" icon={<EditOutlined style={{ color: '#5f6368' }} />} onClick={() => openEditNoteModal(note)} />
                        <Button type="text" icon={<DeleteOutlined style={{ color: '#5f6368' }} />} onClick={() => handleDeleteNote(note.id)} />
                      </Space>
                    }
                    style={{
                      height: '240px',
                      display: 'flex',
                      flexDirection: 'column',
                      backgroundColor: bgColor,
                      borderRadius: 16,
                      boxShadow: 'none',
                      transition: 'box-shadow 0.2s',
                      cursor: 'pointer'
                    }}
                    headStyle={{ borderBottom: 'none', padding: '20px 20px 0 20px', minHeight: 48 }}
                    bodyStyle={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: '12px 20px 20px 20px' }}
                    hoverable
                  >
                    <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
                      <div className="markdown-content" style={{ fontSize: 14, color: '#3c4043', lineHeight: 1.6 }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                          {note.answer}
                        </ReactMarkdown>
                      </div>
                      <div style={{
                        position: 'absolute', bottom: 0, left: 0, right: 0,
                        height: 60, background: `linear-gradient(transparent, ${bgColor})`,
                        pointerEvents: 'none'
                      }} />
                    </div>
                    <div style={{ marginTop: 12, fontSize: 12, color: 'rgba(0,0,0,0.5)', fontWeight: 500, textAlign: 'right' }}>
                      {new Date(note.created_at).toLocaleDateString()}
                    </div>
                  </Card>
                );
              })}
            </div>
          </div>

          <PdfPreviewModal
            open={pdfPreviewVisible}
            documentId={documentId}
            title={document.title}
            initialPage={initialPage}
            initialHighlightKeyword={initialHighlightKeyword}
            onClose={() => {
              setPdfPreviewVisible(false);
              fetchNotes();
            }}
          />
                </>
              ),
            },
            {
              key: "chunks",
              label: (
                <span>
                  <DatabaseOutlined /> 向量塊
                  {chunks && <Badge count={chunks.total} style={{ marginLeft: 6, backgroundColor: "#1677ff" }} />}
                </span>
              ),
              children: (
                <div>
                  {/* 統計列 */}
                  {chunks && (
                    <Row gutter={16} style={{ marginBottom: 16 }}>
                      <Col span={6}><Statistic title="總塊數" value={chunks.total} /></Col>
                      <Col span={6}><Statistic title="總字數" value={chunks.total_chars} /></Col>
                      <Col span={6}><Statistic title="平均每塊字數" value={chunks.avg_chars} /></Col>
                      <Col span={6}>
                        <Space style={{ marginTop: 24 }} wrap>
                          <Button icon={<ReloadOutlined />} onClick={fetchChunks} loading={chunksLoading}>重新載入</Button>
                          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddChunkVisible(true)}>新增手動塊</Button>
                          {selectedChunkIds.length >= 2 && (
                            <Button
                              icon={<MergeCellsOutlined />}
                              onClick={handleMergeChunks}
                              loading={merging}
                              style={{ background: "#722ed1", color: "#fff", borderColor: "#722ed1" }}
                            >
                              合併 ({selectedChunkIds.length}) 塊
                            </Button>
                          )}
                        </Space>
                      </Col>
                    </Row>
                  )}

                  {/* 塊列表 */}
                  <Table
                    loading={chunksLoading}
                    dataSource={chunks?.items ?? []}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    rowSelection={{
                      selectedRowKeys: selectedChunkIds,
                      onChange: (keys) => setSelectedChunkIds(keys),
                    }}
                    columns={[
                      {
                        title: "#",
                        dataIndex: "chunk_index",
                        width: 60,
                        render: (v) => <Typography.Text type="secondary">#{v}</Typography.Text>,
                      },
                      {
                        title: "頁碼",
                        dataIndex: "page",
                        width: 70,
                        render: (v) => v ?? "-",
                      },
                      {
                        title: "字數",
                        dataIndex: "char_count",
                        width: 70,
                        render: (v) => (
                          <span style={{ color: v < 100 ? "#ff4d4f" : v > 1600 ? "#faad14" : "#52c41a" }}>{v}</span>
                        ),
                      },
                      {
                        title: "內容預覽",
                        dataIndex: "text",
                        render: (text, record) => (
                          <div>
                            <Typography.Text
                              style={{ cursor: "pointer" }}
                              onClick={() => setExpandedChunkId(expandedChunkId === record.id ? null : record.id)}
                            >
                              {expandedChunkId === record.id ? text : `${text.slice(0, 120)}${text.length > 120 ? "…" : ""}`}
                            </Typography.Text>
                          </div>
                        ),
                      },
                      {
                        title: "操作",
                        width: 140,
                        render: (_, record) => (
                          <Space>
                            <Tooltip title="編輯並重新向量化">
                              <Button
                                size="small"
                                icon={<EditOutlined />}
                                onClick={() => { setEditingChunk(record); setEditChunkText(record.text); }}
                              />
                            </Tooltip>
                            <Tooltip title="分割此塊">
                              <Button
                                size="small"
                                icon={<ScissorOutlined />}
                                onClick={() => { setSplittingChunk(record); setSplitAt(Math.floor(record.text.length / 2)); }}
                              />
                            </Tooltip>
                            <Popconfirm
                              title="確定刪除此向量塊？"
                              onConfirm={() => handleDeleteChunk(record.id)}
                              okText="刪除"
                              cancelText="取消"
                              okType="danger"
                            >
                              <Tooltip title="刪除">
                                <Button size="small" danger icon={<DeleteOutlined />} />
                              </Tooltip>
                            </Popconfirm>
                          </Space>
                        ),
                      },
                    ]}
                  />
                </div>
              ),
            },
          ]}
        />

        {/* 編輯 Chunk Modal */}
        <Modal
          title={`編輯向量塊 #${editingChunk?.chunk_index ?? ""}`}
          open={!!editingChunk}
          onOk={handleSaveChunk}
          onCancel={() => setEditingChunk(null)}
          confirmLoading={chunkSaving}
          okText="儲存並重新向量化"
          cancelText="取消"
          width={800}
        >
          <Typography.Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
            第 {editingChunk?.page ?? "?"} 頁 ｜ {editChunkText.length} 字
          </Typography.Text>
          <Input.TextArea
            rows={14}
            value={editChunkText}
            onChange={(e) => setEditChunkText(e.target.value)}
            style={{ fontFamily: "monospace", fontSize: 13 }}
          />
        </Modal>

        {/* 分割 Chunk Modal */}
        <Modal
          title={`分割向量塊 #${splittingChunk?.chunk_index ?? ""}`}
          open={!!splittingChunk}
          onOk={handleSplitChunk}
          onCancel={() => setSplittingChunk(null)}
          confirmLoading={splitting}
          okText="分割並重新向量化"
          cancelText="取消"
          width={800}
        >
          {splittingChunk && (
            <div>
              <div style={{ marginBottom: 8 }}>
                <Typography.Text strong>分割位置：第 {splitAt} 字 / 共 {splittingChunk.text.length} 字</Typography.Text>
              </div>
              <Slider
                min={1}
                max={splittingChunk.text.length - 1}
                value={splitAt}
                onChange={setSplitAt}
                style={{ marginBottom: 16 }}
              />
              <div style={{ display: "flex", gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <Typography.Text type="secondary" style={{ display: "block", marginBottom: 4 }}>前半段（{splitAt} 字）</Typography.Text>
                  <div style={{
                    background: "#f6ffed", border: "1px solid #b7eb8f", borderRadius: 4,
                    padding: "8px 12px", fontFamily: "monospace", fontSize: 12,
                    whiteSpace: "pre-wrap", wordBreak: "break-word",
                    maxHeight: 200, overflowY: "auto",
                  }}>
                    {splittingChunk.text.slice(0, splitAt)}
                  </div>
                </div>
                <div style={{ flex: 1 }}>
                  <Typography.Text type="secondary" style={{ display: "block", marginBottom: 4 }}>後半段（{splittingChunk.text.length - splitAt} 字）</Typography.Text>
                  <div style={{
                    background: "#e6f7ff", border: "1px solid #91d5ff", borderRadius: 4,
                    padding: "8px 12px", fontFamily: "monospace", fontSize: 12,
                    whiteSpace: "pre-wrap", wordBreak: "break-word",
                    maxHeight: 200, overflowY: "auto",
                  }}>
                    {splittingChunk.text.slice(splitAt)}
                  </div>
                </div>
              </div>
            </div>
          )}
        </Modal>

        {/* 新增 Chunk Modal */}
        <Modal
          title="新增手動向量塊"
          open={addChunkVisible}
          onOk={handleAddChunk}
          onCancel={() => { setAddChunkVisible(false); setNewChunk({ page: "", text: "" }); }}
          confirmLoading={addingChunk}
          okText="新增並向量化"
          cancelText="取消"
          width={700}
        >
          <div style={{ marginBottom: 12 }}>
            <Typography.Text strong>頁碼（選填）：</Typography.Text>
            <Input
              type="number"
              min={1}
              value={newChunk.page}
              onChange={(e) => setNewChunk({ ...newChunk, page: e.target.value })}
              placeholder="留空表示不指定頁碼"
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Typography.Text strong>文字內容：</Typography.Text>
            <Input.TextArea
              rows={12}
              value={newChunk.text}
              onChange={(e) => setNewChunk({ ...newChunk, text: e.target.value })}
              placeholder="輸入要加入向量索引的文字..."
              style={{ marginTop: 4, fontFamily: "monospace", fontSize: 13 }}
            />
            <Typography.Text type="secondary">{newChunk.text.length} 字</Typography.Text>
          </div>
        </Modal>

          {/* Edit Note Modal */}
          <Modal
            title="編輯筆記"
            open={isEditNoteModalVisible}
            onOk={handleUpdateNote}
            onCancel={() => setIsEditNoteModalVisible(false)}
            width={800}
            okText="儲存"
            cancelText="取消"
          >
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>標題 (問題)：</div>
              <Input
                value={editNoteForm.question}
                onChange={(e) => setEditNoteForm({ ...editNoteForm, question: e.target.value })}
                placeholder="輸入筆記標題..."
              />
            </div>
            <div>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>內容：</div>
              <Input.TextArea
                rows={10}
                value={editNoteForm.answer}
                onChange={(e) => setEditNoteForm({ ...editNoteForm, answer: e.target.value })}
                placeholder="輸入筆記內容 (支援 Markdown)..."
              />
            </div>
          </Modal>

          {/* Create Note Modal */}
          <Modal
            title="建立新筆記"
            open={isCreateNoteModalVisible}
            onOk={handleCreateNote}
            onCancel={() => setIsCreateNoteModalVisible(false)}
            width={800}
            okText="建立"
            cancelText="取消"
          >
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>標題 (問題)：</div>
              <Input
                value={createNoteForm.question}
                onChange={(e) => setCreateNoteForm({ ...createNoteForm, question: e.target.value })}
                placeholder="輸入筆記標題..."
              />
            </div>
            <div>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>內容：</div>
              <Input.TextArea
                rows={10}
                value={createNoteForm.answer}
                onChange={(e) => setCreateNoteForm({ ...createNoteForm, answer: e.target.value })}
                placeholder="輸入筆記內容 (支援 Markdown)..."
              />
            </div>
          </Modal>
        </>
      )}
    </Card>
  );
};

export default DocumentDetail;
