import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { ConfigProvider, App as AntdApp } from "antd";
import zhTW from "antd/locale/zh_TW";

import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DocumentsPage from "./pages/DocumentsPage";
import DocumentCreatePage from "./pages/DocumentCreatePage";
import DocumentDetailPage from "./pages/DocumentDetailPage";
import DocumentEditPage from "./pages/DocumentEditPage";
import QAConsolePage from "./pages/QAConsolePage";
import AdminPage from "./pages/AdminPage";
import VectorSearchTestPage from "./pages/VectorSearchTestPage";
import VectorHealthPage from "./pages/VectorHealthPage";
import PrivateRoute from "./components/PrivateRoute";

function App() {
  return (
    <ConfigProvider locale={zhTW}>
      <AntdApp>
        <Router>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />

            <Route path="/" element={<Navigate to="/documents" replace />} />

            <Route
              path="/documents"
              element={( 
                <PrivateRoute>
                  <DocumentsPage />
                </PrivateRoute>
              )}
            />
            <Route
              path="/documents/new"
              element={( 
                <PrivateRoute>
                  <DocumentCreatePage />
                </PrivateRoute>
              )}
            />
            <Route
              path="/documents/:id"
              element={( 
                <PrivateRoute>
                  <DocumentDetailPage />
                </PrivateRoute>
              )}
            />
            <Route
              path="/documents/:id/edit"
              element={( 
                <PrivateRoute>
                  <DocumentEditPage />
                </PrivateRoute>
              )}
            />
            <Route
              path="/qa"
              element={( 
                <PrivateRoute>
                  <QAConsolePage />
                </PrivateRoute>
              )}
            />
            <Route
              path="/admin/metadata"
              element={(
                <PrivateRoute adminOnly>
                  <AdminPage />
                </PrivateRoute>
              )}
            />
            <Route
              path="/admin/vector-search"
              element={(
                <PrivateRoute adminOnly>
                  <VectorSearchTestPage />
                </PrivateRoute>
              )}
            />
            <Route
              path="/admin/vector-health"
              element={(
                <PrivateRoute adminOnly>
                  <VectorHealthPage />
                </PrivateRoute>
              )}
            />
          </Routes>
        </Router>
      </AntdApp>
    </ConfigProvider>
  );
}

export default App;
