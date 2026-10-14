import { Route, Routes } from "react-router-dom";

import { AppStateProvider } from "./appState";
import AppShell from "./components/AppShell";
import { IndexRunProvider } from "./indexRun";
import ChatPage from "./pages/ChatPage";
import IndexDetailPage from "./pages/IndexDetailPage";
import IndexesPage from "./pages/IndexesPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <AppStateProvider>
      <IndexRunProvider>
        <AppShell>
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/c/:id" element={<ChatPage />} />
            <Route path="/index" element={<IndexesPage />} />
            <Route path="/index/:id" element={<IndexDetailPage />} />
            <Route path="/instellingen" element={<SettingsPage />} />
            <Route path="*" element={<ChatPage />} />
          </Routes>
        </AppShell>
      </IndexRunProvider>
    </AppStateProvider>
  );
}
