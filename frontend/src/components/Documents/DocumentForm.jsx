import React, { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Checkbox, Form, Input, Modal, Radio, Select, Space, Spin, Upload, Typography, message, Divider } from "antd";
import { InboxOutlined, PlusOutlined } from "@ant-design/icons";
import apiClient from "../../services/api";
import AISuggestionModal from "./AISuggestionModal";
import { useTaskStatus } from "../../contexts/TaskStatusContext";

const { Dragger } = Upload;

const DocumentForm = ({ document, onSuccess, onCancel, loading = false }) => {
  const { addTask } = useTaskStatus();
  const [form] = Form.useForm();
  const [metadataFields, setMetadataFields] = useState([]);
  const [classificationOptions, setClassificationOptions] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [processingStatus, setProcessingStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [suggestionState, setSuggestionState] = useState(null);
  const [suggestionVisible, setSuggestionVisible] = useState(false);

  // 新增選項的 Modal 狀態
  const [addOptionModalVisible, setAddOptionModalVisible] = useState(false);
  const [addOptionField, setAddOptionField] = useState(null);
  const [addOptionForm] = Form.useForm();
  const [addingOption, setAddingOption] = useState(false);

  // 強制 VL 視覺解析
  const [forceVision, setForceVision] = useState(false);

  // OCR 相關狀態
  const [ocrModalVisible, setOcrModalVisible] = useState(false);
  const [ocrProcessing, setOcrProcessing] = useState(false);
  const [ocrData, setOcrData] = useState(null); // { filename, total_pages, pdf_temp_path }

  const isEdit = Boolean(document);

  const fetchMetadataFields = async () => {
    try {
      const resp = await apiClient.get("metadata-fields");
      setMetadataFields(resp.data);
    } catch (error) {
      message.error(error.response?.data?.detail ?? "載入中繼資料欄位失敗");
    }
  };

  const fetchClassifications = async () => {
    try {
      const resp = await apiClient.get("documents/classifications");
      setClassificationOptions(resp.data ?? []);
    } catch (error) {
      message.error(error.response?.data?.detail ?? "載入分類清單失敗");
    }
  };

  useEffect(() => {
    fetchMetadataFields();
    fetchClassifications();
  }, []);

  useEffect(() => {
    if (isEdit && document) {
      form.setFieldsValue({
        title: document.title,
        // content 欄位已移除，不需要設置
        metadata: document.metadata ?? {},
        classification_id: document.classification?.id ?? null,
        source_pdf_path: null,
      });
    } else {
      form.resetFields();
    }
  }, [document, isEdit, form]);

  const metadataInitialValues = useMemo(() => {
    if (isEdit && document?.metadata) {
      return document.metadata;
    }
    return {};
  }, [document, isEdit]);

  const findClassificationId = (label) => {
    if (!label) return null;
    const normalized = label.trim().toLowerCase();
    const byName = classificationOptions.find(
      (option) => option.name?.trim().toLowerCase() === normalized,
    );
    if (byName) {
      return byName.id;
    }

    const codeMatch = label.match(/\(([^)]+)\)\s*$/);
    if (codeMatch) {
      const codeNormalized = codeMatch[1].trim().toLowerCase();
      const byCode = classificationOptions.find(
        (option) => option.code && option.code.trim().toLowerCase() === codeNormalized,
      );
      if (byCode) {
        return byCode.id;
      }
    }
    return null;
  };

  // 開啟新增選項 Modal
  const handleOpenAddOption = (field) => {
    setAddOptionField(field);
    setAddOptionModalVisible(true);
    addOptionForm.resetFields();
  };

  // 處理圖片型 PDF（僅支持預覽）
  const handleOcrChoice = async (mode) => {
    if (!ocrData) return;

    try {
      setOcrProcessing(true);
      setOcrModalVisible(false);

      // 建立文件
      setProcessingStatus("正在建立文件...");
      const title = form.getFieldValue("title") || ocrData.filename.replace(/\.pdf$/i, "");
      const metadata = form.getFieldValue("metadata") || {};
      const classification_id = form.getFieldValue("classification_id");

      const payload = {
        title,
        content: "", // 圖片型 PDF 無內容
        metadata,
        classification_id: classification_id || null,
        source_pdf_path: ocrData.pdf_temp_path,
        is_image_based: true, // 標記為圖片型 PDF
      };

      const createResp = await apiClient.post("documents/", payload);
      const documentId = createResp.data.id;

      // 標記為 skipped（僅供預覽）
      await apiClient.post(`documents/${documentId}/ocr/process`, { mode: "skip" });
      message.success("文件已建立（僅支持預覽功能）");
      setProcessingStatus("");
      onSuccess?.();
    } catch (error) {
      message.error(error.response?.data?.detail ?? "處理失敗");
    } finally {
      setOcrProcessing(false);
      setProcessingStatus("");
    }
  };

  // 新增選項
  const handleAddOption = async () => {
    try {
      const values = await addOptionForm.validateFields();
      setAddingOption(true);

      const resp = await apiClient.post(`metadata-fields/${addOptionField.id}/options`, {
        value: values.value,
        display_value: values.display_value,
        order_index: 0,
      });

      const newOption = resp.data;

      // 更新 metadataFields 中的選項列表
      setMetadataFields((prevFields) =>
        prevFields.map((f) => {
          if (f.id === addOptionField.id) {
            return {
              ...f,
              options: [...f.options, newOption],
            };
          }
          return f;
        })
      );

      // 自動選擇新增的選項
      const fieldPath = ["metadata", addOptionField.name];
      form.setFieldValue(fieldPath, newOption.value);

      message.success(`已新增選項：${newOption.display_value}`);
      setAddOptionModalVisible(false);
      addOptionForm.resetFields();
    } catch (error) {
      message.error(error.response?.data?.detail ?? "新增選項失敗");
    } finally {
      setAddingOption(false);
    }
  };

  const handleSubmit = async (values) => {
    console.log('handleSubmit called with values:', values);
    console.log('ocrData:', ocrData);
    console.log('isEdit:', isEdit);

    // 檢查是否有待處理的圖片型 PDF
    if (ocrData && !isEdit) {
      console.log('Opening OCR Modal...');
      // 顯示 OCR Modal 讓用戶選擇處理方式
      setOcrModalVisible(true);
      return;
    }

    const payload = {
      title: values.title,
      content: values.content || null,  // 使用 upload 時提取的 text
      metadata: values.metadata,
    };

    if (values.classification_id) {
      payload.classification_id = values.classification_id;
    }

    const pdfTempPath = form.getFieldValue("source_pdf_path");
    if (pdfTempPath) {
      payload.source_pdf_path = pdfTempPath;
      // VL 模式下不傳 segments，讓後端在向量化時重新用 VL 解析
      if (!forceVision && suggestionState?.segments) {
        payload.segments = suggestionState.segments;
      }
      // 傳遞 AI 生成的文件摘要
      if (suggestionState?.suggestion?.summary) {
        payload.ai_summary = suggestionState.suggestion.summary;
      }
      if (forceVision) {
        payload.force_vision = true;
      }
    }

    try {
      setSubmitting(true);
      if (isEdit) {
        setProcessingStatus("正在更新文件...");
        await apiClient.put(`documents/${document.id}`, payload);
        message.success("文件已更新");
      } else if (forceVision) {
        // VL 模式：立刻建立文件，VL 解析在後台執行
        setProcessingStatus("正在建立文件（VL 解析將在背景執行）...");
        const resp = await apiClient.post("documents/", payload);
        const taskId = resp.data?.task_id;
        const docId = resp.data?.id;
        const docTitle = resp.data?.title ?? payload.title;
        if (taskId && docId) {
          addTask({ task_id: taskId, document_id: docId, document_title: docTitle });
          message.success("文件已建立，VL 視覺解析正在背景執行，可繼續使用系統");
        } else {
          message.success("文件已建立");
        }
      } else {
        setProcessingStatus("正在建立文件並生成向量索引，這可能需要 10-30 秒，請稍候...");
        await apiClient.post("documents/", payload);
        message.success("文件已建立，向量索引已完成");
      }
      onSuccess?.();
    } catch (error) {
      message.error(error.response?.data?.detail ?? "儲存文件時發生錯誤");
    } finally {
      setSubmitting(false);
      setProcessingStatus("");
    }
  };

  const handlePdfUpload = async (file) => {
    const formData = new FormData();
    formData.append("file", file);

    try {
      setUploading(true);
      setProcessingStatus("正在擷取文件內容...");

      const resp = await apiClient.post("documents/upload/", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      // 檢測是否為圖片型 PDF（需要 OCR 處理）
      if (resp.data.is_image_based) {
        setOcrData({
          filename: resp.data.filename,
          total_pages: resp.data.total_pages,
          pdf_temp_path: resp.data.pdf_temp_path,
        });

        form.setFieldsValue({
          title: form.getFieldValue("title") ||
                 (resp.data.filename ? resp.data.filename.replace(/\.pdf$/i, "") : ""),
          source_pdf_path: resp.data.pdf_temp_path,
        });

        setUploading(false);
        setProcessingStatus("");
        // 不立即顯示 OCR Modal，等用戶填寫完必填欄位並點擊建立時再顯示
        message.warning({
          content: `檢測到圖片型 PDF（共 ${resp.data.total_pages} 頁），僅支持預覽功能。請填寫必填欄位後點擊「建立」保存文件。`,
          duration: 5,
        });
        return false;
      }

      setProcessingStatus("正在解析 PDF 並生成 AI 建議...");

      const currentMetadata = form.getFieldValue("metadata") || {};
      const suggestedMetadata = resp.data.suggested_metadata || {};
      const suggestedKeywords = suggestedMetadata.keywords ?? [];
      const mergedKeywords = Array.from(
        new Set([...(currentMetadata.keywords || []), ...suggestedKeywords]),
      );

      const metadataPatch = {
        ...currentMetadata,
        keywords: mergedKeywords,
      };

      if (suggestedMetadata.file_type) {
        metadataPatch.file_type = suggestedMetadata.file_type;
      }
      if (suggestedMetadata.project_id) {
        metadataPatch.project_id = suggestedMetadata.project_id;
      }

      form.setFieldsValue({
        title:
          form.getFieldValue("title") ||
          (resp.data.filename ? resp.data.filename.replace(/\.pdf$/i, "") : ""),
        content: resp.data.text || "",  // 保存 text，避免後端重複提取
        metadata: metadataPatch,
        source_pdf_path: resp.data.pdf_temp_path,
      });

      setSuggestionState({
        suggestion: resp.data.suggestion,
        segments: resp.data.segments ?? [],
        suggestedMetadata,
        text: resp.data.text,  // 保存 text 供後續使用
      });
      setSuggestionVisible(true);

      setProcessingStatus("");
      message.success("PDF 上傳並解析完成");
    } catch (error) {
      message.error(error.response?.data?.detail ?? "上傳 PDF 時發生錯誤");
    } finally {
      setUploading(false);
      setProcessingStatus("");
    }

    return false;
  };

  const handleApplySuggestion = async (editedSuggestion) => {
    const suggestion = editedSuggestion ?? suggestionState?.suggestion;
    if (!suggestion) {
      setSuggestionVisible(false);
      return;
    }

    const { suggestedMetadata } = suggestionState ?? {};
    const currentMetadata = form.getFieldValue("metadata") || {};
    const nextMetadata = { ...currentMetadata };

    // 使用用戶在 Modal 中可能修改過的 keywords
    const mergedKeywords = Array.from(
      new Set([
        ...(Array.isArray(currentMetadata.keywords) ? currentMetadata.keywords : []),
        ...(Array.isArray(suggestion.keywords) ? suggestion.keywords : []),
      ]),
    );
    if (mergedKeywords.length) {
      nextMetadata.keywords = mergedKeywords;
    }

    if (suggestedMetadata?.file_type) {
      nextMetadata.file_type = suggestedMetadata.file_type;
    }

    let classificationId = suggestion.classification_is_new
      ? null
      : findClassificationId(suggestion.classification);

    // 專案只從 metadata 中取得（AI 只會從現有選項中匹配，不會建議新增）
    const projectValue = suggestedMetadata?.project_id;

    const payload = {};
    // 只處理分類的新增建議
    if (suggestion.classification_is_new && suggestion.classification) {
      payload.classification = {
        name: suggestion.classification,
        description: suggestion.classification_reason ?? null,
      };
    }

    if (Object.keys(payload).length > 0) {
      try {
        const resp = await apiClient.post("documents/suggestions/accept", payload);
        const createdClassification = resp.data?.classification;

        if (createdClassification) {
          classificationId = createdClassification.id;
          setClassificationOptions((prev) => {
            if (prev.some((item) => item.id === createdClassification.id)) {
              return prev;
            }
            return [...prev, createdClassification];
          });
        }
      } catch (error) {
        message.error(error.response?.data?.detail ?? "無法新增 AI 建議的分類");
        return;
      }
    }

    if (!classificationId && suggestion.classification && !suggestion.classification_is_new) {
      classificationId = findClassificationId(suggestion.classification);
    }

    const updates = { metadata: nextMetadata };
    if (classificationId) {
      updates.classification_id = classificationId;
    }
    if (projectValue) {
      updates.metadata.project_id = projectValue;
    }

    form.setFieldsValue(updates);
    // 把用戶編輯後的 summary 寫回 state，讓 handleSubmit 能取到最新值
    if (editedSuggestion?.summary !== undefined) {
      setSuggestionState((prev) => ({
        ...prev,
        suggestion: { ...prev.suggestion, summary: editedSuggestion.summary },
      }));
    }
    setSuggestionVisible(false);
    message.success("已套用 AI 建議，請確認內容後再儲存文件");
  };

  const renderMetadataField = (field) => {
    const baseName = ["metadata", field.name];
    const rules = field.is_required
      ? [{ required: true, message: `請填寫「${field.display_name}」` }]
      : [];

    switch (field.field_type) {
      case "text":
      case "textarea":
        return (
          <Form.Item key={field.id} name={baseName} label={field.display_name} rules={rules}>
            <Input.TextArea rows={field.field_type === "textarea" ? 4 : 2} />
          </Form.Item>
        );
      case "number":
        return (
          <Form.Item key={field.id} name={baseName} label={field.display_name} rules={rules}>
            <Input type="number" />
          </Form.Item>
        );
      case "select":
        return (
          <Form.Item key={field.id} name={baseName} label={field.display_name} rules={rules}>
            <Select
              options={field.options.map((opt) => ({
                label: opt.display_value,
                value: opt.value,
              }))}
              dropdownRender={(menu) => (
                <>
                  {menu}
                  <Divider style={{ margin: "8px 0" }} />
                  <Button
                    type="text"
                    icon={<PlusOutlined />}
                    style={{ width: "100%", textAlign: "left" }}
                    onClick={() => handleOpenAddOption(field)}
                  >
                    新增 {field.display_name}
                  </Button>
                </>
              )}
            />
          </Form.Item>
        );
      case "multi_select":
        return (
          <Form.Item key={field.id} name={baseName} label={field.display_name} rules={rules}>
            <Select
              mode="multiple"
              options={field.options.map((opt) => ({
                label: opt.display_value,
                value: opt.value,
              }))}
              dropdownRender={(menu) => (
                <>
                  {menu}
                  <Divider style={{ margin: "8px 0" }} />
                  <Button
                    type="text"
                    icon={<PlusOutlined />}
                    style={{ width: "100%", textAlign: "left" }}
                    onClick={() => handleOpenAddOption(field)}
                  >
                    新增 {field.display_name}
                  </Button>
                </>
              )}
            />
          </Form.Item>
        );
      default:
        return null;
    }
  };

  return (
    <Card title={isEdit ? "編輯文件" : "建立文件"} loading={loading}>
      <Typography.Paragraph type="secondary">
        上傳 PDF 後系統會自動擷取文字與分段資訊，並呼叫 AI 產出繁體中文建議。
      </Typography.Paragraph>
      <Dragger
        multiple={false}
        accept=".pdf"
        beforeUpload={handlePdfUpload}
        showUploadList={false}
        disabled={uploading}
        style={{ marginBottom: 16 }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">點擊或拖曳 PDF 檔案到此上傳</p>
        <p className="ant-upload-hint">僅支援 PDF，系統會即時解析並提供 AI 建議。</p>
      </Dragger>

      <div style={{ marginBottom: 12 }}>
        <Checkbox
          checked={forceVision}
          onChange={(e) => setForceVision(e.target.checked)}
          disabled={uploading}
        >
          強制使用視覺模型解析（適合含表格、欄位對齊或大量圖片的 PDF/PPT 轉檔）
        </Checkbox>
        {forceVision && (
          <Typography.Text type="secondary" style={{ display: "block", marginTop: 4, fontSize: 12 }}>
            解析時間較長（每頁約 10–30 秒），圖片內容也會被描述並納入向量索引。
          </Typography.Text>
        )}
      </div>

      {uploading && (
        <Card style={{ marginBottom: 16 }} size="small">
          <Space direction="vertical" style={{ width: "100%", textAlign: "center" }}>
            <Spin size="large" />
            <Typography.Text strong>{processingStatus}</Typography.Text>
          </Space>
        </Card>
      )}

      {/* 圖片型 PDF 提示 */}
      {ocrData && !isEdit && (
        <Alert
          message="檢測到圖片型 PDF（僅支持預覽）"
          description={`此文件共 ${ocrData.total_pages} 頁，無法直接提取文字。圖片型 PDF 僅支持預覽功能，無法進行全文檢索或 AI 問答。請填寫下方必填欄位後保存文件。`}
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Form
        layout="vertical"
        form={form}
        onFinish={handleSubmit}
        initialValues={{ metadata: metadataInitialValues }}
      >
        <Form.Item name="title" label="標題" rules={[{ required: true, message: "請輸入標題" }]}>
          <Input />
        </Form.Item>

        {/* content 欄位已移除，直接從 PDF 提取，使用 PDF 預覽查看內容 */}
        <Form.Item name="content" hidden>
          <Input type="hidden" />
        </Form.Item>

        <Form.Item name="classification_id" label="分類">
          <Select
            allowClear
            placeholder="選擇分類"
            options={classificationOptions.map((option) => ({
              value: option.id,
              label: option.code ? `${option.name} (${option.code})` : option.name,
            }))}
          />
        </Form.Item>

        <Form.Item name="source_pdf_path" hidden>
          <Input type="hidden" />
        </Form.Item>

        {metadataFields.map((field) => renderMetadataField(field))}

        {submitting && processingStatus && (
          <Card style={{ marginBottom: 16 }} size="small">
            <Space direction="vertical" style={{ width: "100%", textAlign: "center" }}>
              <Spin size="large" />
              <Typography.Text strong>{processingStatus}</Typography.Text>
            </Space>
          </Card>
        )}

        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={submitting} disabled={uploading || submitting}>
              {isEdit ? "更新" : "建立"}
            </Button>
            <Button onClick={onCancel} disabled={submitting}>取消</Button>
          </Space>
        </Form.Item>
      </Form>

      <AISuggestionModal
        open={suggestionVisible}
        suggestion={suggestionState?.suggestion}
        suggestedMetadata={suggestionState?.suggestedMetadata}
        segments={suggestionState?.segments ?? []}
        onApply={handleApplySuggestion}
        onClose={() => setSuggestionVisible(false)}
      />

      {/* 新增選項 Modal */}
      <Modal
        title={`新增${addOptionField?.display_name ?? "選項"}`}
        open={addOptionModalVisible}
        onOk={handleAddOption}
        onCancel={() => {
          setAddOptionModalVisible(false);
          addOptionForm.resetFields();
        }}
        confirmLoading={addingOption}
        okText="新增"
        cancelText="取消"
      >
        <Form form={addOptionForm} layout="vertical">
          <Form.Item
            name="value"
            label="選項值（英文代碼）"
            rules={[
              { required: true, message: "請輸入選項值" },
              { pattern: /^[a-z0-9_-]+$/, message: "只能包含小寫英文、數字、底線和連字號" },
            ]}
            extra="例如：ai_research, project_alpha"
          >
            <Input placeholder="輸入選項值（英文代碼）" />
          </Form.Item>
          <Form.Item
            name="display_value"
            label="顯示名稱"
            rules={[{ required: true, message: "請輸入顯示名稱" }]}
            extra="顯示在介面上的名稱"
          >
            <Input placeholder="輸入顯示名稱" />
          </Form.Item>
        </Form>
      </Modal>

      {/* OCR 選項 Modal */}
      <Modal
        title="圖片型 PDF - 僅支持預覽"
        open={ocrModalVisible}
        onOk={() => handleOcrChoice("skip")}
        onCancel={() => setOcrModalVisible(false)}
        okText="確認並保存"
        cancelText="取消"
        width={600}
      >
        <Space direction="vertical" style={{ width: "100%" }} size="large">
          <Alert
            message="此 PDF 無法提取文字內容"
            description={`這可能是掃描件或傳真文件（共 ${ocrData?.total_pages || "?"} 頁）。圖片型 PDF 僅提供預覽功能，無法進行全文檢索或 AI 問答。`}
            type="warning"
            showIcon
          />

          <Typography.Paragraph>
            <Typography.Text strong>功能限制說明：</Typography.Text>
          </Typography.Paragraph>

          <Typography.Paragraph>
            <ul>
              <li>✓ 可以查看 PDF 預覽</li>
              <li>✓ 可以填寫和管理 metadata</li>
              <li>✗ 無法進行全文檢索</li>
              <li>✗ 無法使用 AI 問答功能</li>
            </ul>
          </Typography.Paragraph>

          <Typography.Paragraph type="secondary">
            點擊「確認並保存」將文件標記為僅供預覽，請確保已填寫必要的 metadata。
          </Typography.Paragraph>
        </Space>
      </Modal>
    </Card>
  );
};

export default DocumentForm;
