import React, { useMemo } from "react";
import { Layout, Menu } from "antd";
import { FileTextOutlined, AppstoreOutlined, SettingOutlined, RobotOutlined } from "@ant-design/icons";
import { useLocation, useNavigate } from "react-router-dom";

const { Sider } = Layout;

const AppSidebar = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const menuItems = [
    { key: "/documents", icon: <FileTextOutlined />, label: "文件列表" },
    { key: "/documents/new", icon: <AppstoreOutlined />, label: "建立文件" },
    { key: "/qa", icon: <RobotOutlined />, label: "RAG智慧問答" },
    { key: "/admin/metadata", icon: <SettingOutlined />, label: "管理介面" },
  ];

  const selectedKey = useMemo(() => {
    if (location.pathname.startsWith("/documents/new")) return "/documents/new";
    if (location.pathname.startsWith("/documents")) return "/documents";
    if (location.pathname.startsWith("/qa")) return "/qa";
    if (location.pathname.startsWith("/admin")) return "/admin/metadata";
    return "/documents";
  }, [location.pathname]);

  return (
    <Sider width={220} theme="dark">
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[selectedKey]}
        items={menuItems}
        onClick={({ key }) => navigate(key)}
        style={{ marginTop: 16 }}
      />
    </Sider>
  );
};

export default AppSidebar;
