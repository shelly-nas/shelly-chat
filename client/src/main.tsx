import "@fontsource/figtree/400.css";
import "@fontsource/figtree/500.css";
import "@fontsource/figtree/600.css";
import "@fontsource/figtree/700.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { ColorModeProvider } from "./colorMode";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ColorModeProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </BrowserRouter>
    </ColorModeProvider>
  </StrictMode>,
);
