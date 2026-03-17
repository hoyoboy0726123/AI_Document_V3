import React, { useMemo } from "react";
import { Layout, Menu } from "antd";
import { FileTextOutlined, AppstoreOutlined, SettingOutlined, RobotOutlined, ThunderboltOutlined, HeartOutlined } from "@ant-design/icons";
import { useLocation, useNavigate } from "react-router-dom";
import FolderTree from "../Folders/FolderTree";

const { Sider } = Layout;

const AppSidebar = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const menuItems = [
    { key: "/documents", icon: <FileTextOutlined />, label: "文件列表" },
    { key: "/documents/new", icon: <AppstoreOutlined />, label: "建立文件" },
    { key: "/qa", icon: <RobotOutlined />, label: "RAG智慧問答" },
    { key: "/admin/metadata", icon: <SettingOutlined />, label: "管理介面" },
    { key: "/admin/vector-search", icon: <ThunderboltOutlined />, label: "向量查詢測試" },
    { key: "/admin/vector-health", icon: <HeartOutlined />, label: "向量庫健康" },
  ];

  const selectedKey = useMemo(() => {
    if (location.pathname.startsWith("/documents/new")) return "/documents/new";
    if (location.pathname.startsWith("/documents")) return "/documents";
    if (location.pathname.startsWith("/qa")) return "/qa";
    if (location.pathname.startsWith("/admin/vector-health")) return "/admin/vector-health";
    if (location.pathname.startsWith("/admin/vector-search")) return "/admin/vector-search";
    if (location.pathname.startsWith("/admin")) return "/admin/metadata";
    return "/documents";
  }, [location.pathname]);

  const isDocuments = location.pathname.startsWith("/documents") && !location.pathname.startsWith("/documents/new");

  return (
    <Sider
      width={220}
      theme="dark"
      style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}
    >
      <div style={{ flex: "0 0 auto" }}>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ marginTop: 16 }}
        />
      </div>

      {isDocuments && (
        <div style={{ flex: "1 1 auto", overflowY: "auto", overflowX: "hidden" }}>
          <FolderTree />
        </div>
      )}
    </Sider>
  );
};

export default AppSidebar;
