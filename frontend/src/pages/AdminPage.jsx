import React, { useEffect, useState } from "react";
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  message,
} from "antd";
import AppLayout from "../components/Layout/AppLayout";
import ClassificationManagement from "../components/Admin/ClassificationManagement";
import ProjectManagement from "../components/Admin/ProjectManagement";
import SystemSettings from "../components/Admin/SystemSettings";
import apiClient from "../services/api";

const fieldTypeOptions = [
  { label: "單行文字", value: "text" },
  { label: "多行文字", value: "textarea" },
  { label: "數字", value: "number" },
  { label: "日期", value: "date" },
  { label: "下拉選單", value: "select" },
  { label: "多選下拉", value: "multi_select" },
];

const AdminPage = () => {
  const [fields, setFields] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fieldModalVisible, setFieldModalVisible] = useState(false);
  const [fieldModalMode, setFieldModalMode] = useState("create");
  const [currentField, setCurrentField] = useState(null);
  const [fieldForm] = Form.useForm();
  const [optionModalVisible, setOptionModalVisible] = useState(false);
  const [optionForm] = Form.useForm();
  const [editingOption, setEditingOption] = useState(null);
  const [optionEditForm] = Form.useForm();

  const fetchFields = async () => {
    try {
      setLoading(true);
      const resp = await apiClient.get("admin/metadata-fields");
      setFields(resp.data);
    } catch (error) {
      message.error(error.response?.data?.detail ?? "載入元數據欄位失敗");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFields();
  }, []);

  useEffect(() => {
    if (currentField) {
      const updated = fields.find((f) => f.id === currentField.id);
      if (updated && updated !== currentField) {
        setCurrentField(updated);
      }
    }
  }, [fields, currentField]);

  const openCreateField = () => {
    setFieldModalMode("create");
    setCurrentField(null);
    fieldForm.resetFields();
    fieldForm.setFieldsValue({ is_required: false, is_active: true, order_index: 0 });
    setFieldModalVisible(true);
  };

  const openEditField = (field) => {
    setFieldModalMode("edit");
    setCurrentField(field);
    fieldForm.setFieldsValue({
      name: field.name,
      display_name: field.display_name,
      field_type: field.field_type,
      is_required: field.is_required,
      is_active: field.is_active,
      order_index: field.order_index,
      description: field.description,
    });
    setFieldModalVisible(true);
  };

  const handleFieldSubmit = async () => {
    try {
      const values = await fieldForm.validateFields();
      if (fieldModalMode === "create") {
        await apiClient.post("admin/metadata-fields/", {
          name: values.name,
          display_name: values.display_name,
          field_type: values.field_type,
          is_required: values.is_required ?? false,
          order_index: values.order_index ?? 0,
          description: values.description ?? null,
        });
        message.success("欄位已建立");
      } else if (currentField) {
        await apiClient.put(`admin/metadata-fields/${currentField.id}/`, {
          display_name: values.display_name,
          field_type: values.field_type,
          is_required: values.is_required,
          is_active: values.is_active,
          order_index: values.order_index,
          description: values.description ?? null,
        });
        message.success("欄位已更新");
      }
      setFieldModalVisible(false);
      fetchFields();
    } catch (error) {
      if (error?.errorFields) return;
      message.error(error.response?.data?.detail ?? "儲存欄位失敗");
    }
  };

  const handleDeleteField = (field) => {
    Modal.confirm({
      title: `刪除欄位 ${field.display_name}`,
      content: "刪除後將無法復原，仍要繼續嗎？",
      okText: "刪除",
      okType: "danger",
      cancelText: "取消",
      async onOk() {
        try {
          await apiClient.delete(`admin/metadata-fields/${field.id}/`);
          message.success("欄位已刪除");
          fetchFields();
        } catch (error) {
          message.error(error.response?.data?.detail ?? "刪除欄位失敗");
        }
      },
    });
  };

  const openOptionModal = (field) => {
    setCurrentField(field);
    optionForm.resetFields();
    setOptionModalVisible(true);
  };

  const handleAddOption = async () => {
    if (!currentField) return;
    try {
      const values = await optionForm.validateFields();
      await apiClient.post(`admin/metadata-fields/${currentField.id}/options/`, {
        value: values.value,
        display_value: values.display_value,
        order_index: values.order_index ?? 0,
      });
      message.success("選項已新增");
      optionForm.resetFields();
      fetchFields();
    } catch (error) {
      if (error?.errorFields) return;
      message.error(error.response?.data?.detail ?? "新增選項失敗");
    }
  };

  const handleToggleOption = async (option) => {
    try {
      await apiClient.put(`admin/metadata-fields/options/${option.id}/`, {
        is_active: !option.is_active,
      });
      fetchFields();
    } catch (error) {
      message.error(error.response?.data?.detail ?? "更新選項狀態失敗");
    }
  };

  const handleDeleteOption = (option) => {
    Modal.confirm({
      title: `刪除選項 ${option.display_value}`,
      okText: "刪除",
      okType: "danger",
      cancelText: "取消",
      async onOk() {
        try {
          await apiClient.delete(`admin/metadata-fields/options/${option.id}/`);
          message.success("選項已刪除");
          fetchFields();
        } catch (error) {
          message.error(error.response?.data?.detail ?? "刪除選項失敗");
        }
      },
    });
  };

  const openEditOption = (option) => {
    setEditingOption(option);
    optionEditForm.setFieldsValue({
      display_value: option.display_value,
      order_index: option.order_index,
      is_active: option.is_active,
    });
  };

  const handleSubmitOptionEdit = async () => {
    if (!editingOption) return;
    try {
      const values = await optionEditForm.validateFields();
      await apiClient.put(`admin/metadata-fields/options/${editingOption.id}/`, {
        display_value: values.display_value,
        order_index: values.order_index,
        is_active: values.is_active,
      });
      message.success("選項已更新");
      setEditingOption(null);
      fetchFields();
    } catch (error) {
      if (error?.errorFields) return;
      message.error(error.response?.data?.detail ?? "更新選項失敗");
    }
  };

  const columns = [
    {
      title: "顯示名稱",
      dataIndex: "display_name",
      key: "display_name",
      render: (text) => <strong>{text}</strong>,
    },
    {
      title: "欄位代碼",
      dataIndex: "name",
      key: "name",
    },
    {
      title: "欄位類型",
      dataIndex: "field_type",
      key: "field_type",
      render: (value) => fieldTypeOptions.find((item) => item.value === value)?.label ?? value,
    },
    {
      title: "必填",
      dataIndex: "is_required",
      key: "is_required",
      render: (value) => (value ? <Tag color="red">必填</Tag> : <Tag>選填</Tag>),
    },
    {
      title: "狀態",
      dataIndex: "is_active",
      key: "is_active",
      render: (value) =>
        value ? (
          <Tag color="green" icon={<CheckCircleOutlined />}>啟用中</Tag>
        ) : (
          <Tag icon={<CloseCircleOutlined />}>已停用</Tag>
        ),
    },
    {
      title: "排序",
      dataIndex: "order_index",
      key: "order_index",
      width: 80,
    },
    {
      title: "操作",
      key: "actions",
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => openEditField(record)}>
            編輯
          </Button>
          {(record.field_type === "select" || record.field_type === "multi_select") && (
            <Button size="small" icon={<SettingOutlined />} onClick={() => openOptionModal(record)}>
              管理選項
            </Button>
          )}
          <Button size="small" danger onClick={() => handleDeleteField(record)}>
            刪除
          </Button>
        </Space>
      ),
    },
  ];

  const tabItems = [
    {
      key: 'metadata',
      label: '元數據欄位管理',
      children: (
        <Card
          title="元數據欄位管理"
          extra={
            <Button type="primary" icon={<AppstoreOutlined />} onClick={openCreateField}>
              新增欄位
            </Button>
          }
        >
        <Table
          rowKey="id"
          loading={loading}
          dataSource={fields}
          columns={columns}
          pagination={false}
          expandable={{
            expandedRowRender: (record) => (
              <div style={{ paddingLeft: 16 }}>
                <strong>欄位說明：</strong> {record.description || "—"}
                {record.options?.length ? (
                  <div style={{ marginTop: 8 }}>
                    <strong>選項：</strong>
                    <Space wrap style={{ marginTop: 8 }}>
                      {record.options.map((opt) => (
                        <Tag key={opt.id} color={opt.is_active ? "blue" : undefined}>
                          {opt.display_value}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                ) : null}
              </div>
            ),
          }}
        />
        </Card>
      ),
    },
    {
      key: 'classifications',
      label: '分類管理',
      children: <ClassificationManagement />,
    },
    {
      key: 'projects',
      label: '專案管理',
      children: <ProjectManagement />,
    },
    {
      key: 'system',
      label: '系統設置',
      children: <SystemSettings />,
    },
  ];

  return (
    <AppLayout>
      <Tabs defaultActiveKey="metadata" items={tabItems} />

      <Modal
        title={fieldModalMode === "create" ? "新增欄位" : "編輯欄位"}
        open={fieldModalVisible}
        onCancel={() => setFieldModalVisible(false)}
        onOk={handleFieldSubmit}
        destroyOnClose
      >
        <Form layout="vertical" form={fieldForm}>
          <Form.Item
            name="name"
            label="欄位代碼"
            rules={[{ required: true, message: "請輸入欄位代碼" }]}
          >
            <Input placeholder="只可輸入英文、數字或底線" disabled={fieldModalMode === "edit"} />
          </Form.Item>
          <Form.Item
            name="display_name"
            label="顯示名稱"
            rules={[{ required: true, message: "請輸入顯示名稱" }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="field_type"
            label="欄位類型"
            rules={[{ required: true, message: "請選擇欄位類型" }]}
          >
            <Select options={fieldTypeOptions} />
          </Form.Item>
          <Form.Item name="is_required" label="是否必填" valuePropName="checked">
            <Switch />
          </Form.Item>
          {fieldModalMode === "edit" && (
            <Form.Item name="is_active" label="是否啟用" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
          <Form.Item name="order_index" label="排序">
            <Input type="number" placeholder="0" />
          </Form.Item>
          <Form.Item name="description" label="欄位說明">
            <Input.TextArea rows={3} placeholder="可填寫欄位用途或限制" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={currentField ? `管理選項 - ${currentField.display_name}` : "管理選項"}
        open={optionModalVisible}
        onCancel={() => setOptionModalVisible(false)}
        footer={null}
        destroyOnClose
        width={640}
      >
        {currentField && (
          <>
            <Form layout="inline" form={optionForm} style={{ marginBottom: 16 }}>
              <Form.Item
                name="value"
                rules={[{ required: true, message: "請輸入選項代碼" }]}
              >
                <Input placeholder="選項代碼" />
              </Form.Item>
              <Form.Item
                name="display_value"
                rules={[{ required: true, message: "請輸入顯示名稱" }]}
              >
                <Input placeholder="顯示名稱" />
              </Form.Item>
              <Form.Item name="order_index">
                <Input type="number" placeholder="排序" style={{ width: 100 }} />
              </Form.Item>
              <Form.Item>
                <Button type="primary" onClick={handleAddOption}>
                  新增選項
                </Button>
              </Form.Item>
            </Form>

            <Table
              dataSource={fields.find((f) => f.id === currentField.id)?.options ?? []}
              rowKey="id"
              pagination={false}
              columns={[
                { title: "選項代碼", dataIndex: "value", key: "value" },
                { title: "顯示名稱", dataIndex: "display_value", key: "display_value" },
                { title: "排序", dataIndex: "order_index", key: "order_index", width: 80 },
                {
                  title: "狀態",
                  dataIndex: "is_active",
                  key: "is_active",
                  render: (value) => (value ? <Tag color="blue">啟用</Tag> : <Tag>停用</Tag>),
                },
                {
                  title: "操作",
                  key: "option_actions",
                  render: (_, option) => (
                    <Space>
                      <Button size="small" onClick={() => openEditOption(option)}>
                        編輯
                      </Button>
                      <Button size="small" onClick={() => handleToggleOption(option)}>
                        {option.is_active ? "停用" : "啟用"}
                      </Button>
                      <Button size="small" danger onClick={() => handleDeleteOption(option)}>
                        刪除
                      </Button>
                    </Space>
                  ),
                },
              ]}
            />
          </>
        )}
      </Modal>

      <Modal
        title="編輯選項"
        open={Boolean(editingOption)}
        onCancel={() => setEditingOption(null)}
        onOk={handleSubmitOptionEdit}
        destroyOnClose
      >
        <Form layout="vertical" form={optionEditForm}>
          <Form.Item
            name="display_value"
            label="顯示名稱"
            rules={[{ required: true, message: "請輸入顯示名稱" }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="order_index" label="排序">
            <Input type="number" placeholder="0" />
          </Form.Item>
          <Form.Item name="is_active" label="是否啟用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </AppLayout>
  );
};

export default AdminPage;

