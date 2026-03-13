import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  Divider,
  Alert,
  message,
} from "antd";
import { DeleteOutlined, SendOutlined, QuestionCircleOutlined, StopOutlined } from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import AppLayout from "../components/Layout/AppLayout";
import apiClient from "../services/api";
import PdfPreviewModal from "../components/Documents/PdfPreviewModal";

const { Title, Paragraph, Text } = Typography;

const QAConsolePage = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [classifications, setClassifications] = useState([]);
  const [projectOptions, setProjectOptions] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [pdfPreview, setPdfPreview] = useState({ open: false, documentId: null, title: "", page: 1 });
  const [followupQuestion, setFollowupQuestion] = useState("");
  const [expandedSnippets, setExpandedSnippets] = useState({});
  const conversationEndRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversationHistory]);

  const stopInFlight = () => {
    try { abortRef.current?.abort(); } catch {}
    abortRef.current = null;
    setLoading(false);
    message.info("已停止查詢");
  };

  const loadInitialData = async () => {
    try {
      const [classificationResp, metadataResp, documentsResp] = await Promise.all([
        apiClient.get("documents/classifications"),
        apiClient.get("metadata-fields"),
        apiClient.get("documents", { params: { page: 1, page_size: 200 } }),
      ]);

      setClassifications(classificationResp.data ?? []);
      const fields = metadataResp.data ?? [];
      const projectField = fields.find((field) => field.name === "project_id");
      setProjectOptions(projectField?.options ?? []);
      setDocuments(documentsResp.data?.items ?? []);
    } catch (error) {
      message.error(error.response?.data?.detail ?? "初始化載入失敗");
    }
  };

  useEffect(() => {
    loadInitialData();
    const savedHistory = localStorage.getItem("qa_conversation_history");
    if (savedHistory) {
      try { setConversationHistory(JSON.parse(savedHistory)); } catch {}
    }
  }, []);

  useEffect(() => {
    if (conversationHistory.length > 0) {
      localStorage.setItem("qa_conversation_history", JSON.stringify(conversationHistory));
    }
  }, [conversationHistory]);

  const postRag = async (payload) => {
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const resp = await apiClient.post("rag/query", payload, { signal: controller.signal });
      return resp.data || {};
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  const handleSubmit = async (values, useAiFallback = false) => {
    const question = values.question?.trim();
    if (!question) { message.warning("請輸入問題"); return; }
    const payload = {
      question,
      top_k: values.top_k ?? 5,
      classification_id: values.classification_id || null,
      project_id: values.project_id || null,
      document_id: values.document_id || null,
      conversation_history: conversationHistory,
      use_ai_fallback: useAiFallback,
      skip_ai_understanding: true,
    };
    try {
      const data = await postRag(payload);
      const newMessage = {
        question,
        answer: data?.answer ?? "",
        sources: data?.sources ?? [],
        is_followup: data?.is_followup ?? false,
        optimized_query: data?.optimized_query,
        suggested_questions: data?.suggested_questions ?? [],
        used_ai_fallback: data?.used_ai_fallback ?? false,
        timestamp: new Date().toISOString(),
      };
      setConversationHistory((prev) => [...prev, newMessage]);
      form.setFieldValue("question", "");
    } catch (error) {
      const msg = error?.message || error?.response?.data?.detail || "查詢失敗";
      if (/abort|canceled/i.test(String(msg))) message.info("已停止查詢"); else message.error(msg);
    }
  };

  const handleFollowupSubmit = async () => {
    const question = followupQuestion?.trim();
    if (!question) { message.warning("請輸入追問內容"); return; }
    const currentFormValues = form.getFieldsValue();
    const payload = {
      question,
      top_k: currentFormValues.top_k ?? 5,
      classification_id: currentFormValues.classification_id || null,
      project_id: currentFormValues.project_id || null,
      document_id: currentFormValues.document_id || null,
      conversation_history: conversationHistory,
      use_ai_fallback: false,
      skip_ai_understanding: false,
    };
    try {
      const data = await postRag(payload);
      const newMessage = {
        question,
        answer: data?.answer ?? "",
        sources: data?.sources ?? [],
        is_followup: data?.is_followup ?? false,
        optimized_query: data?.optimized_query,
        suggested_questions: data?.suggested_questions ?? [],
        used_ai_fallback: data?.used_ai_fallback ?? false,
        timestamp: new Date().toISOString(),
      };
      setConversationHistory((prev) => [...prev, newMessage]);
      setFollowupQuestion("");
    } catch (error) {
      const msg = error?.message || error?.response?.data?.detail || "查詢失敗";
      if (/abort|canceled/i.test(String(msg))) message.info("已停止查詢"); else message.error(msg);
    }
  };

  const handleAiFallback = async (question) => {
    const currentFormValues = form.getFieldsValue();
    const payload = {
      question,
      top_k: currentFormValues.top_k ?? 5,
      classification_id: currentFormValues.classification_id || null,
      project_id: currentFormValues.project_id || null,
      document_id: currentFormValues.document_id || null,
      conversation_history: conversationHistory,
      use_ai_fallback: true,
    };
    try {
      const data = await postRag(payload);
      const newMessage = {
        question,
        answer: data?.answer ?? "",
        sources: data?.sources ?? [],
        is_followup: data?.is_followup ?? false,
        optimized_query: data?.optimized_query,
        suggested_questions: data?.suggested_questions ?? [],
        used_ai_fallback: data?.used_ai_fallback ?? false,
        timestamp: new Date().toISOString(),
      };
      setConversationHistory((prev) => [...prev, newMessage]);
    } catch (error) {
      const msg = error?.message || error?.response?.data?.detail || "查詢失敗";
      if (/abort|canceled/i.test(String(msg))) message.info("已停止查詢"); else message.error(msg);
    }
  };

  const clearHistory = () => {
    setConversationHistory([]);
    localStorage.removeItem("qa_conversation_history");
    message.success("對話歷史已清除");
  };

  const openPdfPreview = (source) => {
    const page = source.page && source.page > 0 ? source.page : 1;
    setPdfPreview({ open: true, documentId: source.document_id, title: source.title, page });
  };

  const classificationOptions = useMemo(
    () => classifications.map((item) => ({ value: item.id, label: item.code ? `${item.name} (${item.code})` : item.name })),
    [classifications]
  );
  const projectSelectOptions = useMemo(
    () => projectOptions.map((item) => ({ value: item.value, label: item.display_value })),
    [projectOptions]
  );
  const documentSelectOptions = useMemo(
    () => documents.map((item) => ({ value: item.id, label: item.title })),
    [documents]
  );

  return (
    <AppLayout>
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="查詢設定" style={{ position: "sticky", top: 16 }}>
            <Form form={form} layout="vertical" initialValues={{ top_k: 5 }} onFinish={handleSubmit}>
              <Form.Item name="question" label="請輸入問題" rules={[{ required: true, message: "請輸入想查詢的問題" }]}>
                <Input.TextArea rows={4} placeholder="例：某規範流程？或追問上一題關鍵數值" allowClear onPressEnter={(e) => { if (e.ctrlKey || e.metaKey) { form.submit(); } }} />
              </Form.Item>
              <Form.Item name="classification_id" label="分類">
                <Select allowClear showSearch placeholder="選擇分類（可留空）" options={classificationOptions} optionFilterProp="label" />
              </Form.Item>
              <Form.Item name="project_id" label="專案">
                <Select allowClear showSearch placeholder="選擇專案（可留空）" options={projectSelectOptions} optionFilterProp="label" />
              </Form.Item>
              <Form.Item name="document_id" label="文件">
                <Select allowClear showSearch placeholder="選擇文件（可留空）" options={documentSelectOptions} optionFilterProp="label" />
              </Form.Item>
              <Form.Item name="top_k" label="來源筆數">
                <InputNumber min={1} max={10} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item>
                <Space style={{ width: "100%" }}>
                  <Button type="primary" htmlType="submit" loading={loading} icon={<SendOutlined />} block>
                    送出查詢 (Ctrl+Enter)
                  </Button>
                  {loading && (
                    <Button danger icon={<StopOutlined />} onClick={stopInFlight}>
                      停止
                    </Button>
                  )}
                  {conversationHistory.length > 0 && (
                    <Button onClick={clearHistory} icon={<DeleteOutlined />} danger>
                      清除歷史
                    </Button>
                  )}
                </Space>
              </Form.Item>
              <Alert message="提示" description="此為新問題輸入，問題將直接用於文字檢索；追問會使用 AI 理解功能，請使用右側下方的追問輸入。" type="info" showIcon icon={<QuestionCircleOutlined />} />
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title={`對話記錄 (${conversationHistory.length})`}>
            {conversationHistory.length === 0 ? (
              <Empty description="尚未開始對話，請先在左側輸入問題以開始查詢" style={{ padding: "48px 0" }} />
            ) : (
              <div style={{ maxHeight: "calc(100vh - 200px)", overflowY: "auto", padding: "0 8px" }}>
                {conversationHistory.map((message, index) => (
                  <div key={index} style={{ marginBottom: 32 }}>
                    <div style={{ marginBottom: 16 }}>
                      <Tag color="blue" style={{ fontSize: 14, padding: "4px 12px" }}>問題 {index + 1}</Tag>
                      {message.is_followup && (<Tag color="orange" style={{ marginLeft: 8 }}>追問</Tag>)}
                      <Text strong style={{ fontSize: 16, marginLeft: 8 }}>{message.question}</Text>
                      {message.optimized_query && message.optimized_query !== message.question && (
                        <div style={{ marginTop: 8, paddingLeft: 12, borderLeft: "3px solid #1890ff" }}>
                          <Text type="secondary" style={{ fontSize: 13 }}>AI 理解：{message.optimized_query}</Text>
                        </div>
                      )}
                    </div>
                    <Card size="small" style={{ background: "#f9f9f9", borderLeft: message.used_ai_fallback ? "4px solid #faad14" : "4px solid #52c41a" }}>
                      {message.used_ai_fallback && (
                        <Alert message="AI 一般知識回答" description="此答案由 AI 一般知識庫產生，可能不來自系統文件內容" type="warning" showIcon style={{ marginBottom: 12 }} />
                      )}
                      <div style={{ fontSize: 15, lineHeight: 1.8 }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.answer}</ReactMarkdown>
                      </div>
                      {message.sources.length > 0 && (
                        <div style={{ marginTop: 16 }}>
                          <Divider orientation="left" style={{ fontSize: 13, marginTop: 16, marginBottom: 12 }}>參考來源({message.sources.length})</Divider>
                          <List size="small" dataSource={message.sources} renderItem={(source, idx) => {
                            const needsTruncate = (source.snippet || "").length > 180;
                            const snippet = needsTruncate ? (source.snippet || "").slice(0, 180) : (source.snippet || "");
                            return (
                              <List.Item key={`${index}-${idx}`}>
                                <List.Item.Meta
                                  title={
                                    <Space size={8} wrap>
                                      <Tag color="green">來源 {idx + 1}</Tag>
                                      <Text>{source.title || "(未命名文件)"}{typeof source.page === "number" ? ` - 第 ${source.page} 頁` : ""}</Text>
                                      {source.score != null && (<Text type="secondary">(相似度 {source.score.toFixed(3)})</Text>)}
                                      <Button size="small" onClick={() => openPdfPreview(source)}>預覽</Button>
                                    </Space>
                                  }
                                  description={
                                    <div>
                                      <Text style={{ whiteSpace: "pre-wrap" }}>{snippet}{needsTruncate ? "..." : ""}</Text>
                                    </div>
                                  }
                                />
                              </List.Item>
                            );
                          }} />
                        </div>
                      )}
                    </Card>
                    {index < conversationHistory.length - 1 && <Divider />}
                  </div>
                ))}
                <div ref={conversationEndRef} />
              </div>
            )}
            {loading && (<div style={{ textAlign: "center", padding: 24 }}><Spin size="large" tip="AI 正在思考並查詢中..." /></div>)}
            {conversationHistory.length > 0 && (
              <div style={{ marginTop: 16, borderTop: "2px solid #e8e8e8", paddingTop: 12 }}>
                <div style={{ marginBottom: 8, fontSize: 13, color: "#52c41a" }}>
                  <QuestionCircleOutlined style={{ marginRight: 6 }} />
                  追問輸入列 - AI 將延續上下文並優化您的提示
                </div>
                <Space.Compact style={{ width: "100%" }}>
                  <Input.TextArea value={followupQuestion} onChange={(e) => setFollowupQuestion(e.target.value)} placeholder="例如：想知道更多？更詳細說明？" rows={1} autoSize={{ minRows: 1, maxRows: 4 }} onPressEnter={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); handleFollowupSubmit(); } }} disabled={loading} />
                  <Button type="primary" icon={<SendOutlined />} onClick={handleFollowupSubmit} loading={loading}>追問</Button>
                  {loading && (<Button danger icon={<StopOutlined />} onClick={stopInFlight}>停止</Button>)}
                </Space.Compact>
              </div>
            )}
          </Card>
        </Col>
      </Row>
      <PdfPreviewModal open={pdfPreview.open} documentId={pdfPreview.documentId} title={pdfPreview.title} initialPage={pdfPreview.page} onClose={() => setPdfPreview({ open: false, documentId: null, title: "", page: 1 })} />
    </AppLayout>
  );
};

export default QAConsolePage;
