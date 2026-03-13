import React from "react";
import { Badge, Button, Divider, List, Modal, Space, Tag, Typography } from "antd";

const { Paragraph, Text, Title } = Typography;

const renderSuggestionRow = (label, value, isNew, reason) => {
  if (!value) {
    return (
      <div style={{ marginBottom: 12 }}>
        <Text strong>{label}：</Text> <Text type="secondary">目前沒有建議</Text>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <Space size="small" align="baseline">
        <Text strong>{label}：</Text>
        <Text>{value}</Text>
        {isNew ? <Tag color="volcano">新增</Tag> : <Tag color="blue">既有</Tag>}
      </Space>
      {reason && (
        <Paragraph style={{ marginBottom: 0, marginLeft: 24 }} type="secondary">
          {reason}
        </Paragraph>
      )}
    </div>
  );
};

const AISuggestionModal = ({
  open,
  suggestion,
  suggestedMetadata,
  segments,
  onApply,
  onClose,
}) => {
  const hasSuggestion =
    suggestion &&
    (suggestion.summary ||
      suggestion.classification ||
      suggestion.project ||
      (suggestion.keywords && suggestion.keywords.length > 0));

  return (
    <Modal
      open={open}
      title="AI 智慧建議"
      onCancel={onClose}
      width={800}
      footer={[
        <Button key="close" onClick={onClose}>
          關閉
        </Button>,
        <Button key="apply" type="primary" onClick={onApply} disabled={!hasSuggestion}>
          套用建議
        </Button>,
      ]}
    >
      {!hasSuggestion && (
        <Paragraph type="secondary">
          目前沒有可套用的 AI 建議，您仍可依照上方欄位自行填寫並儲存文件。
        </Paragraph>
      )}

      {hasSuggestion && (
        <>
          {suggestion.summary && (
            <>
              <Title level={5} style={{ marginTop: 0 }}>
                摘要
              </Title>
              <Paragraph>{suggestion.summary}</Paragraph>
              <Divider />
            </>
          )}

          <Title level={5} style={{ marginTop: 0 }}>
            分類與專案
          </Title>
          {renderSuggestionRow(
            "分類",
            suggestion.classification,
            suggestion.classification_is_new,
            suggestion.classification_reason
          )}
          {renderSuggestionRow(
            "專案",
            suggestion.project,
            suggestion.project_is_new,
            suggestion.project_reason
          )}

          <Divider />

          <Title level={5}>關鍵字</Title>
          {suggestion.keywords && suggestion.keywords.length > 0 ? (
            <Space wrap>
              {suggestion.keywords.map((keyword) => (
                <Tag key={keyword}>{keyword}</Tag>
              ))}
            </Space>
          ) : (
            <Paragraph type="secondary">沒有建議的關鍵字。</Paragraph>
          )}

          <Divider />

          <Title level={5}>中繼資料建議</Title>
          {suggestedMetadata && Object.keys(suggestedMetadata).length > 0 ? (
            <Space direction="vertical" size="small" style={{ width: "100%" }}>
              {Object.entries(suggestedMetadata).map(([key, value]) => (
                <Badge.Ribbon key={key} text={key}>
                  <div style={{ background: "#fafafa", padding: 8, borderRadius: 4 }}>
                    <Text>{Array.isArray(value) ? value.join("、") : value}</Text>
                  </div>
                </Badge.Ribbon>
              ))}
            </Space>
          ) : (
            <Paragraph type="secondary">沒有額外的中繼資料建議。</Paragraph>
          )}
        </>
      )}

      <Divider />

      <Title level={5}>文字分段</Title>
      {segments && segments.length > 0 ? (
        <List
          size="small"
          dataSource={segments.slice(0, 10)}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Text strong>
                    第 {item.page} 頁，第 {item.paragraph_index} 段
                  </Text>
                }
                description={<Text>{item.text}</Text>}
              />
            </List.Item>
          )}
        />
      ) : (
        <Paragraph type="secondary">目前沒有可顯示的分段內容。</Paragraph>
      )}
      {segments && segments.length > 10 && (
        <Paragraph type="secondary" style={{ marginTop: 8 }}>
          僅顯示前 10 筆，共 {segments.length} 筆分段。
        </Paragraph>
      )}
    </Modal>
  );
};

export default AISuggestionModal;
