import { Route, Routes } from "react-router-dom";

import { AppStateProvider } from "./appState";
import AppShell from "./components/AppShell";
import ChatPage from "./pages/ChatPage";
import IndexPage from "./pages/IndexPage";

export default function App() {
  return (
    <AppStateProvider>
      <AppShell>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/c/:id" element={<ChatPage />} />
          <Route path="/index" element={<IndexPage />} />
          <Route path="*" element={<ChatPage />} />
        </Routes>
      </AppShell>
    </AppStateProvider>
  );
}
