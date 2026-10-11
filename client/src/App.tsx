import { Route, Routes } from "react-router-dom";

import { AppStateProvider } from "./appState";
import AppShell from "./components/AppShell";
import ChatPage from "./pages/ChatPage";
import IndexDetailPage from "./pages/IndexDetailPage";
import IndexesPage from "./pages/IndexesPage";

export default function App() {
  return (
    <AppStateProvider>
      <AppShell>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/c/:id" element={<ChatPage />} />
          <Route path="/index" element={<IndexesPage />} />
          <Route path="/index/:id" element={<IndexDetailPage />} />
          <Route path="*" element={<ChatPage />} />
        </Routes>
      </AppShell>
    </AppStateProvider>
  );
}
