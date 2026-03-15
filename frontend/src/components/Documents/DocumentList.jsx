
import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  message,
  Divider,
  List,
  Typography,
} from 'antd';
import { DeleteOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, DownloadOutlined, UpOutlined } from '@ant-design/icons';
import apiClient from '../../services/api';
import PdfPreviewModal from './PdfPreviewModal';

const DEFAULT_PAGE_SIZE = 10;

const KeywordList = ({ keywords }) => {
  const [expanded, setExpanded] = useState(false);

  if (!Array.isArray(keywords) || keywords.length === 0) {
    return '-';
  }

  if (keywords.length <= 3) {
    return (
      <Space wrap>
        {keywords.map((kw) => (
          <Tag key={kw}>{kw}</Tag>
        ))}
      </Space>
    );
  }

  if (expanded) {
    return (
      <Space wrap>
        {keywords.map((kw) => (
          <Tag key={kw}>{kw}</Tag>
        ))}
        <Tag
          icon={<UpOutlined />}
          style={{ cursor: 'pointer', borderStyle: 'dashed' }}
          onClick={(e) => {
            e.stopPropagation();
            setExpanded(false);
          }}
        >
          收起
        </Tag>
      </Space>
    );
  }

  return (
    <Space wrap>
      {keywords.slice(0, 3).map((kw) => (
        <Tag key={kw}>{kw}</Tag>
      ))}
      <Tag
        style={{ cursor: 'pointer', borderStyle: 'dashed' }}
        onClick={(e) => {
          e.stopPropagation();
          setExpanded(true);
        }}
      >
        +{keywords.length - 3}
      </Tag>
    </Space>
  );
};

const DocumentList = ({ onCreate, onView }) => {

  const [loading, setLoading] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [filterForm] = Form.useForm();
  const [metadataFields, setMetadataFields] = useState([]);
  const [crossDocSearch, setCrossDocSearch] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [showSearchResults, setShowSearchResults] = useState(false);

  // PDF 預覽狀態
  const [pdfPreviewVisible, setPdfPreviewVisible] = useState(false);
  const [previewDocumentId, setPreviewDocumentId] = useState(null);
  const [previewDocumentTitle, setPreviewDocumentTitle] = useState('');
  const [previewInitialPage, setPreviewInitialPage] = useState(1);
  const [previewHighlightKeyword, setPreviewHighlightKeyword] = useState('');

  const fetchDocuments = async (params = {}) => {
    try {
      setLoading(true);
      const filterValues = filterForm.getFieldsValue();
      const resp = await apiClient.get('documents/', {
        params: {
          page,
          page_size: pageSize,
          search_term: filterValues.search_term,
          file_type: filterValues.file_type,
          project_id: filterValues.project_id,
          keywords: filterValues.keywords?.join(',') ?? undefined,
          ...params,
        },
      });
      console.log('API 回應資料:', resp.data.items);
      if (resp.data.items.length > 0) {
        console.log('第一筆文件資料:', resp.data.items[0]);
        console.log('metadata:', resp.data.items[0].metadata);
        console.log('classification:', resp.data.items[0].classification);
      }
      setDocuments(resp.data.items);
      setTotal(resp.data.total);
    } catch (error) {
      message.error(error.response?.data?.detail ?? '載入文件列表失敗');
    } finally {
      setLoading(false);
    }
  };

  const fetchMetadataFields = async () => {
    try {
      const resp = await apiClient.get('metadata-fields');
      console.log('載入的 metadata fields:', resp.data);
      setMetadataFields(resp.data);

      // Debug: 檢查各個欄位的選項
      resp.data.forEach(field => {
        if (['file_type', 'project_id', 'keywords'].includes(field.name)) {
          console.log(`${field.name} options:`, field.options?.length || 0);
        }
      });
    } catch (error) {
      console.error('無法載入元數據欄位', error);
    }
  };

  useEffect(() => {
    fetchMetadataFields();
  }, []);

  useEffect(() => {
    fetchDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize]);

  const handleSearch = () => {
    setPage(1);
    fetchDocuments({ page: 1 });
  };

  const handleReset = () => {
    filterForm.resetFields();
    setPage(1);
    fetchDocuments({
      page: 1,
      search_term: undefined,
      file_type: undefined,
      project_id: undefined,
      keywords: undefined,
    });
  };

  const handleDelete = async (documentId) => {
    try {
      await apiClient.delete(`documents/${documentId}`);
      message.success('文件已刪除');
      fetchDocuments();
    } catch (error) {
      message.error(error.response?.data?.detail ?? '刪除文件失敗');
    }
  };

  const handleCrossDocSearch = async () => {
    const query = crossDocSearch.trim();
    if (!query) {
      message.warning('請輸入搜尋關鍵字');
      return;
    }

    setSearching(true);
    try {
      const filterValues = filterForm.getFieldsValue();
      const response = await apiClient.get('documents/search-text-all', {
        params: {
          q: query,
          classification_id: filterValues.classification_id,
          file_type: filterValues.file_type,
          project_id: filterValues.project_id,
        },
      });
      setSearchResults(response.data.matches);
      setShowSearchResults(true);
      message.success(
        `找到 ${response.data.total_matches} 個匹配結果（跨 ${response.data.total_documents} 份文件）`
      );
    } catch (error) {
      message.error(error.response?.data?.detail ?? '搜尋失敗');
    } finally {
      setSearching(false);
    }
  };

  const handleClearSearch = () => {
    setCrossDocSearch('');
    setSearchResults([]);
    setShowSearchResults(false);
  };

  const handleSearchResultClick = (item) => {
    // 直接在當前頁面打開 PDF 預覽，而不是跳轉到詳情頁
    const keyword = crossDocSearch.trim();
    console.log('點擊搜索結果:', {
      documentId: item.document_id,
      title: item.document_title,
      page: item.page,
      keyword: keyword
    });

    setPreviewDocumentId(item.document_id);
    setPreviewDocumentTitle(item.document_title);
    setPreviewInitialPage(item.page);
    setPreviewHighlightKeyword(keyword);
    setPdfPreviewVisible(true);
  };

  const handleClosePdfPreview = () => {
    setPdfPreviewVisible(false);
    // 保留搜索結果，用戶可以繼續查看下一個結果
  };

  const keywordOptions = useMemo(() => {
    const keywordsField = metadataFields.find((field) => field.name === 'keywords');
    return (
      keywordsField?.options?.map((opt) => ({
        label: opt.display_value,
        value: opt.value,
      })) ?? []
    );
  }, [metadataFields]);

  const selectOptions = (fieldName) =>
    metadataFields
      .find((item) => item.name === fieldName)
      ?.options?.map((opt) => ({ label: opt.display_value, value: opt.value })) ?? [];

  // 根據欄位名稱和值，查找對應的顯示名稱
  const getDisplayValue = (fieldName, value) => {
    if (!value) return null;
    const field = metadataFields.find((item) => item.name === fieldName);
    if (!field || !field.options) return value;
    const option = field.options.find((opt) => opt.value === value);
    return option ? option.display_value : value;
  };

  const handleDownload = async (record) => {
    try {
      const response = await apiClient.get(`documents/${record.id}/pdf`, {
        responseType: 'blob',
      });

      // Create a blob link to download
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;

      // Try to get filename from content-disposition header or fallback
      let filename = `${record.title}.pdf`;
      const contentDisposition = response.headers['content-disposition'];
      if (contentDisposition) {
        // Try to match filename*=utf-8''encoded_filename
        const filenameStarMatch = contentDisposition.match(/filename\*=utf-8''([^;]+)/i);
        if (filenameStarMatch && filenameStarMatch.length === 2) {
          filename = decodeURIComponent(filenameStarMatch[1]);
        } else {
          // Fallback to filename="filename"
          const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
          if (filenameMatch && filenameMatch.length === 2) {
            filename = filenameMatch[1];
          }
        }
      }

      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download error:', error);
      message.error('下載失敗');
    }
  };

  const columns = [
    {
      title: '標題',
      dataIndex: 'title',
      render: (text, record) => (
        <Button type="link" onClick={() => onView?.(record)}>
          {text}
        </Button>
      ),
    },
    {
      title: '文件類型',
      dataIndex: ['metadata', 'file_type'],
      render: (value) => {
        const displayValue = getDisplayValue('file_type', value);
        return displayValue ? <Tag color="blue">{displayValue}</Tag> : '-';
      },
    },
    {
      title: '所屬專案',
      dataIndex: ['metadata', 'project_id'],
      render: (value) => {
        const displayValue = getDisplayValue('project_id', value);
        return displayValue ? <Tag color="purple">{displayValue}</Tag> : '-';
      },
    },
    {
      title: '關鍵字',
      dataIndex: ['metadata', 'keywords'],
      render: (keywords) => <KeywordList keywords={keywords} />,
    },
    {
      title: '分類結果',
      dataIndex: 'classification',
      render: (classification) => {
        if (!classification) return <Tag>尚未分類</Tag>;
        const displayText = classification.code
          ? `${classification.name} (${classification.code})`
          : classification.name;
        return <Tag color="green">{displayText}</Tag>;
      },
    },

    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => onView?.(record)}>
            檢視
          </Button>
          <Button
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => handleDownload(record)}
          >
            下載
          </Button>
          <Popconfirm
            title="確認刪除"
            description="確定要刪除此文件嗎？此操作將同時刪除相關的向量資料和 PDF 檔案，無法復原。"
            onConfirm={() => handleDelete(record.id)}
            okText="確定"
            cancelText="取消"
            okType="danger"
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              刪除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="文件列表"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => fetchDocuments()}>
            重新整理
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => onCreate?.()}>
            建立文件
          </Button>
        </Space>
      }
    >
      {/* 跨文件全文檢索 */}
      <div style={{ marginBottom: 16 }}>
        <Space.Compact style={{ width: '100%', maxWidth: 600 }}>
          <Input
            placeholder="跨文件全文檢索..."
            value={crossDocSearch}
            onChange={(e) => setCrossDocSearch(e.target.value)}
            onPressEnter={handleCrossDocSearch}
            prefix={<SearchOutlined />}
            allowClear
          />
          <Button type="primary" loading={searching} onClick={handleCrossDocSearch}>
            搜尋
          </Button>
          {showSearchResults && (
            <Button onClick={handleClearSearch}>清除結果</Button>
          )}
        </Space.Compact>
      </div>

      {/* 搜尋結果顯示 */}
      {showSearchResults && searchResults.length > 0 && (
        <Card
          size="small"
          title={`搜尋結果 (${searchResults.length} 筆)`}
          style={{ marginBottom: 16 }}
          bodyStyle={{ maxHeight: '300px', overflowY: 'auto' }}
        >
          <List
            size="small"
            dataSource={searchResults}
            renderItem={(item) => (
              <List.Item
                style={{ cursor: 'pointer' }}
                onClick={() => handleSearchResultClick(item)}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Typography.Text strong>{item.document_title}</Typography.Text>
                      <Tag color="blue">第 {item.page} 頁</Tag>
                    </Space>
                  }
                  description={
                    <Typography.Text type="secondary">
                      {item.snippet}
                    </Typography.Text>
                  }
                />
              </List.Item>
            )}
          />
        </Card>
      )}

      {showSearchResults && searchResults.length === 0 && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Typography.Text type="secondary">未找到匹配的結果</Typography.Text>
        </Card>
      )}

      <Divider style={{ margin: '16px 0' }} />

      <Form form={filterForm} layout="inline" onFinish={handleSearch} style={{ marginBottom: 16 }}>
        <Form.Item name="search_term" label="關鍵字">
          <Input placeholder="輸入標題關鍵字" allowClear />
        </Form.Item>
        <Form.Item name="file_type" label="文件類型">
          <Select
            placeholder="選擇文件類型"
            options={selectOptions('file_type')}
            allowClear
            style={{ width: 180 }}
          />
        </Form.Item>
        <Form.Item name="project_id" label="所屬專案">
          <Select
            placeholder="選擇專案"
            options={selectOptions('project_id')}
            allowClear
            style={{ width: 180 }}
          />
        </Form.Item>
        <Form.Item name="keywords" label="關鍵字標籤">
          <Select
            mode="multiple"
            allowClear
            placeholder="選擇關鍵字"
            style={{ minWidth: 240 }}
            options={keywordOptions}
          />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              搜尋
            </Button>
            <Button onClick={handleReset}>重設</Button>
          </Space>
        </Form.Item>
      </Form>

      <Table
        rowKey="id"
        dataSource={documents}
        columns={columns}
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: (newPage, newSize) => {
            setPage(newPage);
            setPageSize(newSize);
          },
        }}
      />

      {/* PDF 預覽 Modal */}
      <PdfPreviewModal
        open={pdfPreviewVisible}
        documentId={previewDocumentId}
        title={previewDocumentTitle}
        initialPage={previewInitialPage}
        initialHighlightKeyword={previewHighlightKeyword}
        onClose={handleClosePdfPreview}
      />
    </Card>
  );
};

export default DocumentList;

