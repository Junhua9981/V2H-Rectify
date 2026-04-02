import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import UploadPage from "./pages/UploadPage";
import ResultPage from "./pages/ResultPage";
import BatchUploadPage from "./pages/BatchUploadPage";
import BatchResultPage from "./pages/BatchResultPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<UploadPage />} />
        <Route path="/result" element={<ResultPage />} />
        <Route path="/batch" element={<BatchUploadPage />} />
        <Route path="/batch/result" element={<BatchResultPage />} />
      </Routes>
    </Layout>
  );
}

