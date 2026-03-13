import React, { useEffect, useState } from "react";
import { Button, Card, Descriptions, Space, Tag, message, Modal, Input } from "antd";
import { FilePdfOutlined, ExclamationCircleOutlined, EditOutlined, DeleteOutlined, BookOutlined, PlusOutlined } from "@ant-design/icons";
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

  // 整份文件 AI 分析狀態
  // 重新向量化狀態
  const [reVectorizing, setReVectorizing] = useState(false);

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
              fetchNotes(); // Refresh notes when closing preview
            }}
          />

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
