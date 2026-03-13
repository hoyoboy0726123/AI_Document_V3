
import React from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import AppLayout from '../components/Layout/AppLayout';
import DocumentDetail from '../components/Documents/DocumentDetail';

const DocumentDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { initialPage, initialHighlightKeyword } = location.state || {};

  return (
    <AppLayout>
      <DocumentDetail
        documentId={id}
        initialPage={initialPage}
        initialHighlightKeyword={initialHighlightKeyword}
        onBack={() => navigate('/documents')}
        onEdit={(doc) => navigate(`/documents/${doc.id}/edit`)}
      />
    </AppLayout>
  );
};

export default DocumentDetailPage;
