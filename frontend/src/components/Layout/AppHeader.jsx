import React from "react";
import { Layout, Typography, Button } from "antd";
import useAuthStore from "../../stores/authStore";

const { Header } = Layout;
const { Title, Text } = Typography;

const AppHeader = () => {
  const { user, logout } = useAuthStore();

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  return (
    <Header
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        background: "#fff",
        padding: "0 24px",
        borderBottom: "1px solid #eee",
      }}
    >
      <Title level={4} style={{ margin: 0 }}>
        智慧文件管理系統
      </Title>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <Text strong>{user?.username}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {user?.role}
          </Text>
        </div>
        <Button onClick={handleLogout}>登出</Button>
      </div>
    </Header>
  );
};

export default AppHeader;
