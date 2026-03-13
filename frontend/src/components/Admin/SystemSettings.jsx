import React, { useEffect, useState } from "react";
import {
  Card,
  Button,
  message,
  Statistic,
  Row,
  Col,
  Alert,
  Modal,
  Spin,
  Form,
  InputNumber,
  Switch,
  Divider,
  Space,
} from "antd";
import {
  DatabaseOutlined,
  DeleteOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  SaveOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  EyeOutlined,
} from "@ant-design/icons";
import apiClient from "../../services/api";

const SystemSettings = () => {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [savingQuery, setSavingQuery] = useState(false);
  const [savingVector, setSavingVector] = useState(false);
  const [queryForm] = Form.useForm();
  const [vectorForm] = Form.useForm();

  // 載入系統配置
  const fetchConfig = async () => {
    try {
      setLoading(true);
      const resp = await apiClient.get("admin/system-config");
      setConfig(resp.data);

      // 設置表單初始值
      if (resp.data.vector_config) {
        // 查詢參數表單
        queryForm.setFieldsValue({
          min_similarity_score: resp.data.vector_config.min_similarity_score,
          default_top_k: resp.data.vector_config.default_top_k,
          search_multiplier: resp.data.vector_config.search_multiplier,
        });

        // 向量化參數表單
        vectorForm.setFieldsValue({
          overlap_chars: resp.data.vector_config.overlap_chars,
          max_chars: resp.data.vector_config.max_chars,
          overlap_enabled: resp.data.vector_config.overlap_chars > 0,
        });
      }
    } catch (error) {
      message.error("載入系統配置失敗");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  // 保存查詢參數配置（立即生效，無需重新向量化）
  const handleSaveQueryConfig = async (values) => {
    try {
      setSavingQuery(true);

      // 獲取當前的向量化參數
      const currentVectorConfig = config?.vector_config || {};

      // 合併配置：保持向量化參數不變，只更新查詢參數
      const configData = {
        overlap_chars: currentVectorConfig.overlap_chars || 0,
        max_chars: currentVectorConfig.max_chars || 1800,
        min_similarity_score: values.min_similarity_score,
        default_top_k: values.default_top_k,
        search_multiplier: values.search_multiplier,
      };

      await apiClient.put("admin/vector-config", configData);
      message.success("查詢參數已成功保存，立即生效！");
      fetchConfig();
    } catch (error) {
      message.error(error.response?.data?.detail ?? "保存配置失敗");
    } finally {
      setSavingQuery(false);
    }
  };

  // 保存向量化參數配置（需要重新向量化才能生效）
  const handleSaveVectorConfig = async (values) => {
    try {
      setSavingVector(true);

      // 獲取當前的查詢參數
      const currentVectorConfig = config?.vector_config || {};

      // 根據開關決定 overlap_chars 的值
      const configData = {
        overlap_chars: values.overlap_enabled ? values.overlap_chars : 0,
        max_chars: values.max_chars,
        min_similarity_score: currentVectorConfig.min_similarity_score || 0.3,
        default_top_k: currentVectorConfig.default_top_k || 5,
        search_multiplier: currentVectorConfig.search_multiplier || 10,
      };

      await apiClient.put("admin/vector-config", configData);
      message.success("向量化參數已成功保存，請刪除向量並重新向量化文件！");
      fetchConfig();
    } catch (error) {
      message.error(error.response?.data?.detail ?? "保存配置失敗");
    } finally {
      setSavingVector(false);
    }
  };

  // 刪除所有向量值
  const handleClearVectors = () => {
    Modal.confirm({
      title: "確認刪除所有向量值",
      icon: <WarningOutlined />,
      content: (
        <div>
          <p>此操作將刪除所有文件的向量數據。</p>
          <p><strong>注意事項：</strong></p>
          <ul>
            <li>保留所有文件和文本內容</li>
            <li>刪除所有向量（embeddings）</li>
            <li>刪除 FAISS 向量索引</li>
            <li>刪除後可使用「重新向量化」功能重建</li>
            <li>RAG 搜索功能將暫時不可用</li>
          </ul>
          <p>當前文件數量：<strong>{config?.total_documents || 0}</strong></p>
          <p>當前向量塊數量：<strong>{config?.total_chunks || 0}</strong></p>
        </div>
      ),
      okText: "確認刪除",
      cancelText: "取消",
      okType: "danger",
      onOk: async () => {
        try {
          setClearing(true);
          message.loading("正在刪除向量值，請稍候...", 0);

          const resp = await apiClient.post("admin/clear-vectors");

          message.destroy();
          message.success(
            `成功刪除所有向量值（共 ${resp.data.cleared_chunks} 個 chunks）`
          );

          fetchConfig();
        } catch (error) {
          message.destroy();
          message.error(error.response?.data?.detail ?? "刪除向量值失敗");
        } finally {
          setClearing(false);
        }
      },
    });
  };

  if (loading && !config) {
    return (
      <Card>
        <div style={{ textAlign: "center", padding: "40px 0" }}>
          <Spin size="large" />
        </div>
      </Card>
    );
  }

  return (
    <div>
      {/* 系統狀態 */}
      <Card title="系統狀態" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={6}>
            <Statistic
              title="Embedding 模型"
              value={config?.embedding_model || "-"}
              prefix={<DatabaseOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="LLM 模型"
              value={config?.llm_model || "-"}
              prefix={<RobotOutlined />}
            />
          </Col>
          <Col span={4}>
            <Statistic
              title="文件總數"
              value={config?.total_documents || 0}
              prefix={<CheckCircleOutlined />}
            />
          </Col>
          <Col span={4}>
            <Statistic
              title="向量塊總數"
              value={config?.total_chunks || 0}
              prefix={<DatabaseOutlined />}
            />
          </Col>
          <Col span={4}>
            <Statistic
              title="FAISS 索引"
              value={config?.faiss_index_exists ? "已建立" : "未建立"}
              valueStyle={{
                color: config?.faiss_index_exists ? "#3f8600" : "#cf1322",
              }}
            />
          </Col>
        </Row>

        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={6}>
            <Statistic
              title="Vision 模型"
              value={config?.vision_model || "-"}
              prefix={<EyeOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="Ollama 版本"
              value={config?.ollama_version || "-"}
              prefix={<ToolOutlined />}
            />
          </Col>
        </Row>

        <Alert
          message="模型說明"
          description={
            <div>
              <p><strong>Embedding 模型：</strong>用於文本向量化（需要在 .env 中修改 OLLAMA_EMBED_MODEL）</p>
              <p><strong>LLM 模型：</strong>用於生成回答和分析（需要在 .env 中修改 OLLAMA_LLM_MODEL）</p>
              <p><strong>Vision 模型：</strong>用於處理 PDF 圖片辨識（需要在 .env 中修改 OLLAMA_VISION_MODEL）</p>
            </div>
          }
          type="info"
          showIcon
          style={{ marginTop: 16 }}
        />
      </Card>

      {/* 查詢參數配置（立即生效） */}
      <Card
        title={
          <span>
            <ThunderboltOutlined style={{ marginRight: 8 }} />
            查詢參數配置（立即生效）
          </span>
        }
        style={{ marginBottom: 16 }}
      >
        <Alert
          message="這些參數可以隨時調整，保存後立即生效，無需重新向量化文件"
          description={
            <div>
              <p><strong>適用場景：</strong>微調搜索效果、調整返回結果數量、過濾低相關結果</p>
              <p><strong>優點：</strong>調整方便，可以即時測試不同參數對搜索結果的影響</p>
            </div>
          }
          type="success"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <Form
          form={queryForm}
          layout="vertical"
          onFinish={handleSaveQueryConfig}
          initialValues={{
            min_similarity_score: 0.3,
            default_top_k: 5,
            search_multiplier: 10,
          }}
        >
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                label="向量匹配閾值"
                name="min_similarity_score"
                rules={[{ required: true, message: '請輸入閾值' }]}
                extra="低於此分數的結果將被過濾（0-1）。建議 0.2-0.4"
              >
                <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>

            <Col span={8}>
              <Form.Item
                label="預設返回來源數"
                name="default_top_k"
                rules={[{ required: true, message: '請輸入數量' }]}
                extra="預設返回多少個相關來源。建議 3-10"
              >
                <InputNumber min={1} max={20} style={{ width: '100%' }} />
              </Form.Item>
            </Col>

            <Col span={8}>
              <Form.Item
                label="搜索倍數"
                name="search_multiplier"
                rules={[{ required: true, message: '請輸入倍數' }]}
                extra="實際搜索數量 = 返回數 × 倍數。建議 5-15"
              >
                <InputNumber min={1} max={20} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Divider />

          <Form.Item>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SaveOutlined />}
                loading={savingQuery}
                size="large"
              >
                保存查詢參數
              </Button>
              <Button
                onClick={() => queryForm.resetFields()}
                size="large"
              >
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {/* 向量化參數配置（需重新向量化） */}
      <Card
        title={
          <span>
            <ToolOutlined style={{ marginRight: 8 }} />
            向量化參數配置（需重新向量化）
          </span>
        }
        style={{ marginBottom: 16 }}
      >
        <Alert
          message="修改這些參數後，必須刪除所有向量值並重新向量化所有文件才能生效"
          description={
            <div>
              <p><strong>適用場景：</strong>優化文本切塊方式、調整向量塊大小</p>
              <p><strong>注意：</strong>修改後需要執行以下步驟：</p>
              <ol style={{ marginBottom: 0 }}>
                <li>保存配置</li>
                <li>到下方「向量管理」點擊「刪除所有向量值」</li>
                <li>到各文件詳情頁點擊「重新向量化」按鈕</li>
              </ol>
            </div>
          }
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <Form
          form={vectorForm}
          layout="vertical"
          onFinish={handleSaveVectorConfig}
          initialValues={{
            overlap_enabled: true,
            overlap_chars: 250,
            max_chars: 1800,
          }}
        >
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label="向量塊重疊 (Overlap)"
                name="overlap_enabled"
                valuePropName="checked"
              >
                <Switch
                  checkedChildren="啟用"
                  unCheckedChildren="停用"
                />
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) =>
                  prevValues.overlap_enabled !== currentValues.overlap_enabled
                }
              >
                {({ getFieldValue }) =>
                  getFieldValue('overlap_enabled') ? (
                    <Form.Item
                      label="重疊字符數"
                      name="overlap_chars"
                      rules={[{ required: true, message: '請輸入重疊字符數' }]}
                      extra="建議 200-300 字。重疊可以避免重要資訊被切斷。"
                    >
                      <InputNumber min={0} max={500} style={{ width: '100%' }} />
                    </Form.Item>
                  ) : (
                    <Alert
                      message="已停用重疊功能"
                      description="向量塊之間不會有重疊內容，可能導致跨段落資訊遺失"
                      type="warning"
                      showIcon
                      style={{ marginBottom: 16 }}
                    />
                  )
                }
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item
                label="向量塊最大字符數"
                name="max_chars"
                rules={[{ required: true, message: '請輸入最大字符數' }]}
                extra="每個向量塊的最大長度。建議 1500-2000 字。"
              >
                <InputNumber min={500} max={3000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Divider />

          <Form.Item>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SaveOutlined />}
                loading={savingVector}
                size="large"
              >
                保存向量化參數
              </Button>
              <Button
                onClick={() => vectorForm.resetFields()}
                size="large"
              >
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {/* 向量管理 */}
      <Card title="向量管理">
        <Alert
          message="刪除所有向量值說明"
          description={
            <div>
              <p>刪除所有向量值將保留所有文件和文本內容，只刪除向量數據（embeddings）和 FAISS 索引。</p>
              <p><strong>何時需要刪除向量值：</strong></p>
              <ul style={{ marginBottom: 0 }}>
                <li>更改了 embedding 模型（例如從 text-embedding-004 升級到 gemini-embedding-001）</li>
                <li>修改了向量處理參數（overlap、max_chars 等）</li>
                <li>FAISS 索引損壞或向量維度不匹配</li>
                <li>想要重新開始建立向量索引</li>
              </ul>
              <p style={{ marginTop: 8 }}>
                <strong>刪除後：</strong>可以使用各文件詳情頁的「重新向量化」按鈕來重建向量（無需重新上傳 PDF）。
              </p>
            </div>
          }
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <Button
          type="primary"
          danger
          icon={<DeleteOutlined />}
          onClick={handleClearVectors}
          loading={clearing}
          size="large"
        >
          刪除所有向量值
        </Button>
      </Card>
    </div>
  );
};

export default SystemSettings;
