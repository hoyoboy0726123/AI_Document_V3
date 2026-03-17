import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Row,
  Select,
  Space,
  Tag,
  Typography,
  Divider,
  Alert,
  message,
} from "antd";
import { BulbOutlined, DeleteOutlined, SendOutlined, QuestionCircleOutlined, StopOutlined } from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import AppLayout from "../components/Layout/AppLayout";
import apiClient from "../services/api";
import useAuthStore from "../stores/authStore";
import PdfPreviewModal from "../components/Documents/PdfPreviewModal";

const { Title, Paragraph, Text } = Typography;

const QAConsolePage = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [streamingMsg, setStreamingMsg] = useState(null);
  // streamingMsg: { question, thinking, answer, isStreaming, thinkingDone, sources, is_followup, optimized_query }
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
  }, [conversationHistory, streamingMsg?.answer]);

  const stopInFlight = () => {
    try { abortRef.current?.abort(); } catch {}
    abortRef.current = null;
    setLoading(false);
    setStreamingMsg(null);
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

  // Helper: get auth token
  const getToken = () => {
    let token = useAuthStore.getState().token;
    if (!token) {
      try {
        const persisted = JSON.parse(window.localStorage.getItem("auth-storage") || "{}");
        token = persisted?.state?.token;
      } catch {}
    }
    return token;
  };

  // Streaming RAG via SSE
  const postRagStream = async (payload, { onThinking, onContent, onSources, onDone, onError }) => {
    const token = getToken();
    const controller = new AbortController();
    abortRef.current = controller;

    const resp = await fetch("/api/v1/rag/query/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try { const err = await resp.json(); detail = err.detail || detail; } catch {}
      throw new Error(detail);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep incomplete last line

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;
        try {
          const event = JSON.parse(jsonStr);
          if (event.type === "thinking") onThinking?.(event.text || "");
          else if (event.type === "content") onContent?.(event.text || "");
          else if (event.type === "sources") onSources?.(event);
          else if (event.type === "done") onDone?.();
          else if (event.type === "error") onError?.(event.message);
        } catch {}
      }
    }
  };

  const runStream = async (payload, question) => {
    setLoading(true);
    setStreamingMsg({ question, thinking: "", answer: "", isStreaming: true, thinkingDone: false, sources: [], is_followup: false, optimized_query: null });

    try {
      await postRagStream(payload, {
        onThinking: (text) =>
          setStreamingMsg((prev) => prev ? { ...prev, thinking: prev.thinking + text } : null),
        onContent: (text) =>
          setStreamingMsg((prev) => prev ? { ...prev, answer: prev.answer + text } : null),
        onSources: (event) =>
          setStreamingMsg((prev) =>
            prev ? {
              ...prev,
              sources: event.sources ?? [],
              is_followup: event.is_followup ?? false,
              optimized_query: event.optimized_query ?? null,
              thinkingDone: true,
            } : null
          ),
        onDone: () => {
          setStreamingMsg((prev) => {
            if (!prev) return null;
            const newMsg = {
              question: prev.question,
              answer: prev.answer,
              sources: prev.sources,
              is_followup: prev.is_followup,
              optimized_query: prev.optimized_query,
              thinking: prev.thinking,
              suggested_questions: [],
              used_ai_fallback: false,
              timestamp: new Date().toISOString(),
            };
            setConversationHistory((h) => [...h, newMsg]);
            return null;
          });
          setLoading(false);
          abortRef.current = null;
        },
        onError: (errMsg) => {
          message.error(errMsg || "串流查詢失敗");
          setStreamingMsg(null);
          setLoading(false);
          abortRef.current = null;
        },
      });
    } catch (err) {
      const msg = err?.message || "查詢失敗";
      if (/abort|cancel/i.test(String(msg))) message.info("已停止查詢"); else message.error(msg);
      setStreamingMsg(null);
      setLoading(false);
      abortRef.current = null;
    }
  };

  const handleSubmit = async (values) => {
    const question = values.question?.trim();
    if (!question) { message.warning("請輸入問題"); return; }
    const payload = {
      question,
      top_k: values.top_k ?? 5,
      classification_id: values.classification_id || null,
      project_id: values.project_id || null,
      document_id: values.document_id || null,
      conversation_history: conversationHistory,
      use_ai_fallback: false,
      skip_ai_understanding: true,
    };
    form.setFieldValue("question", "");
    await runStream(payload, question);
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
    setFollowupQuestion("");
    await runStream(payload, question);
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
    setLoading(true);
    try {
      const resp = await apiClient.post("rag/query", payload, { signal: new AbortController().signal });
      const data = resp.data || {};
      setConversationHistory((prev) => [...prev, {
        question,
        answer: data?.answer ?? "",
        sources: data?.sources ?? [],
        is_followup: false,
        optimized_query: null,
        thinking: "",
        suggested_questions: [],
        used_ai_fallback: true,
        timestamp: new Date().toISOString(),
      }]);
    } catch (error) {
      const msg = error?.message || error?.response?.data?.detail || "查詢失敗";
      if (!/abort|cancel/i.test(String(msg))) message.error(msg);
    } finally {
      setLoading(false);
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

  // Shared ReactMarkdown components for styled table rendering
  const markdownComponents = {
    table: ({ node, ...props }) => (
      <div style={{ overflowX: "auto", marginBottom: 8 }}>
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 14 }} {...props} />
      </div>
    ),
    thead: ({ node, ...props }) => <thead style={{ background: "#fafafa" }} {...props} />,
    th: ({ node, ...props }) => (
      <th style={{ border: "1px solid #d9d9d9", padding: "6px 12px", fontWeight: 600, textAlign: "left", whiteSpace: "nowrap" }} {...props} />
    ),
    td: ({ node, ...props }) => (
      <td style={{ border: "1px solid #d9d9d9", padding: "6px 12px" }} {...props} />
    ),
    tr: ({ node, ...props }) => <tr style={{ borderBottom: "1px solid #f0f0f0" }} {...props} />,
  };

  // Render thinking collapse for a message (history or live)
  const renderThinking = (thinking, isLive, thinkingDone) => {
    if (!thinking) return null;
    const labelText = isLive && !thinkingDone ? "思考中..." : "思考過程";
    // Force-expand only while streaming thinking; afterwards let user control it freely
    const forceProps = isLive && !thinkingDone ? { activeKey: ["t"] } : {};
    return (
      <Collapse
        size="small"
        style={{ marginBottom: 12, background: "#fffbe6", border: "1px solid #ffe58f" }}
        {...forceProps}
        items={[{
          key: "t",
          label: (
            <Text type="secondary" style={{ fontSize: 12 }}>
              <BulbOutlined style={{ marginRight: 4 }} />{labelText}
            </Text>
          ),
          children: (
            <Text style={{ fontSize: 12, whiteSpace: "pre-wrap", color: "#888" }}>{thinking}</Text>
          ),
        }]}
      />
    );
  };

  // Render source list
  const renderSources = (sources, msgIndex) => {
    if (!sources || sources.length === 0) return null;
    return (
      <div style={{ marginTop: 16 }}>
        <Divider orientation="left" style={{ fontSize: 13, marginTop: 16, marginBottom: 12 }}>
          參考來源({sources.length})
        </Divider>
        <List
          size="small"
          dataSource={sources}
          renderItem={(source, idx) => {
            const key = `${msgIndex}-${idx}`;
            const isExpanded = !!expandedSnippets[key];
            const full = source.snippet || "";
            const needsTruncate = full.length > 200;
            const displaySnippet = needsTruncate && !isExpanded ? full.slice(0, 200) : full;
            return (
              <List.Item key={key}>
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
                      <Text style={{ whiteSpace: "pre-wrap" }}>
                        {displaySnippet}{needsTruncate && !isExpanded ? "..." : ""}
                      </Text>
                      {needsTruncate && (
                        <Button
                          type="link"
                          size="small"
                          style={{ padding: "0 0 0 4px", height: "auto", fontSize: 12 }}
                          onClick={() => setExpandedSnippets((prev) => ({ ...prev, [key]: !prev[key] }))}
                        >
                          {isExpanded ? "收起" : "展開全文"}
                        </Button>
                      )}
                    </div>
                  }
                />
              </List.Item>
            );
          }}
        />
      </div>
    );
  };

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
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  <Button type="primary" htmlType="submit" loading={loading} icon={<SendOutlined />} style={{ flex: "1 1 auto" }}>
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
                </div>
              </Form.Item>
              <Alert message="提示" description="此為新問題輸入，問題將直接用於文字檢索；追問會使用 AI 理解功能，請使用右側下方的追問輸入。" type="info" showIcon icon={<QuestionCircleOutlined />} />
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title={`對話記錄 (${conversationHistory.length})`}>
            {conversationHistory.length === 0 && !streamingMsg ? (
              <Empty description="尚未開始對話，請先在左側輸入問題以開始查詢" style={{ padding: "48px 0" }} />
            ) : (
              <div style={{ maxHeight: "calc(100vh - 200px)", overflowY: "auto", padding: "0 8px" }}>
                {/* Completed conversation history */}
                {conversationHistory.map((msg, index) => (
                  <div key={index} style={{ marginBottom: 32 }}>
                    <div style={{ marginBottom: 16 }}>
                      <Tag color="blue" style={{ fontSize: 14, padding: "4px 12px" }}>問題 {index + 1}</Tag>
                      {msg.is_followup && (<Tag color="orange" style={{ marginLeft: 8 }}>追問</Tag>)}
                      <Text strong style={{ fontSize: 16, marginLeft: 8 }}>{msg.question}</Text>
                      {msg.optimized_query && msg.optimized_query !== msg.question && (
                        <div style={{ marginTop: 8, paddingLeft: 12, borderLeft: "3px solid #1890ff" }}>
                          <Text type="secondary" style={{ fontSize: 13 }}>AI 理解：{msg.optimized_query}</Text>
                        </div>
                      )}
                    </div>
                    <Card size="small" style={{ background: "#f9f9f9", borderLeft: msg.used_ai_fallback ? "4px solid #faad14" : "4px solid #52c41a" }}>
                      {msg.used_ai_fallback && (
                        <Alert message="AI 一般知識回答" description="此答案由 AI 一般知識庫產生，可能不來自系統文件內容" type="warning" showIcon style={{ marginBottom: 12 }} />
                      )}
                      {/* Thinking section: collapsed by default in history */}
                      {renderThinking(msg.thinking, false, true)}
                      <div style={{ fontSize: 15, lineHeight: 1.8 }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{msg.answer}</ReactMarkdown>
                      </div>
                      {renderSources(msg.sources, index)}
                    </Card>
                    {(index < conversationHistory.length - 1 || streamingMsg) && <Divider />}
                  </div>
                ))}

                {/* Live streaming message */}
                {streamingMsg && (
                  <div style={{ marginBottom: 32 }}>
                    <div style={{ marginBottom: 16 }}>
                      <Tag color="blue" style={{ fontSize: 14, padding: "4px 12px" }}>問題 {conversationHistory.length + 1}</Tag>
                      {streamingMsg.is_followup && <Tag color="orange" style={{ marginLeft: 8 }}>追問</Tag>}
                      <Text strong style={{ fontSize: 16, marginLeft: 8 }}>{streamingMsg.question}</Text>
                      {streamingMsg.optimized_query && streamingMsg.optimized_query !== streamingMsg.question && (
                        <div style={{ marginTop: 8, paddingLeft: 12, borderLeft: "3px solid #1890ff" }}>
                          <Text type="secondary" style={{ fontSize: 13 }}>AI 理解：{streamingMsg.optimized_query}</Text>
                        </div>
                      )}
                    </div>
                    <Card size="small" style={{ background: "#f9f9f9", borderLeft: "4px solid #52c41a" }}>
                      {/* Thinking: expanded while thinking, collapsed after done */}
                      {renderThinking(streamingMsg.thinking, true, streamingMsg.thinkingDone)}
                      <div style={{ fontSize: 15, lineHeight: 1.8 }}>
                        {streamingMsg.answer ? (
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{streamingMsg.answer}</ReactMarkdown>
                        ) : (
                          <Text type="secondary" style={{ fontStyle: "italic" }}>
                            {streamingMsg.thinkingDone ? "生成回答中..." : "AI 思考中..."}
                          </Text>
                        )}
                      </div>
                      {streamingMsg.thinkingDone && renderSources(streamingMsg.sources, "live")}
                    </Card>
                  </div>
                )}

                <div ref={conversationEndRef} />
              </div>
            )}

            {/* Followup input */}
            {(conversationHistory.length > 0 || streamingMsg) && (
              <div style={{ marginTop: 16, borderTop: "2px solid #e8e8e8", paddingTop: 12 }}>
                <div style={{ marginBottom: 8, fontSize: 13, color: "#52c41a" }}>
                  <QuestionCircleOutlined style={{ marginRight: 6 }} />
                  追問輸入列 - AI 將延續上下文並優化您的提示
                </div>
                <Space.Compact style={{ width: "100%" }}>
                  <Input.TextArea
                    value={followupQuestion}
                    onChange={(e) => setFollowupQuestion(e.target.value)}
                    placeholder="例如：想知道更多？更詳細說明？"
                    rows={1}
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    onPressEnter={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); handleFollowupSubmit(); } }}
                    disabled={loading}
                  />
                  <Button type="primary" icon={<SendOutlined />} onClick={handleFollowupSubmit} loading={loading}>追問</Button>
                  {loading && (<Button danger icon={<StopOutlined />} onClick={stopInFlight}>停止</Button>)}
                </Space.Compact>
              </div>
            )}
          </Card>
        </Col>
      </Row>
      <PdfPreviewModal
        open={pdfPreview.open}
        documentId={pdfPreview.documentId}
        title={pdfPreview.title}
        initialPage={pdfPreview.page}
        onClose={() => setPdfPreview({ open: false, documentId: null, title: "", page: 1 })}
      />
    </AppLayout>
  );
};

export default QAConsolePage;
