// Light/dark mode: follows the system until the user picks one, and remembers
// that choice in localStorage.
import { CssBaseline, PaletteMode, ThemeProvider, createTheme, useMediaQuery } from "@mui/material";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { themeSettings } from "./theme";

const KEY = "shelly-chat.color-mode";

interface ColorMode {
  mode: PaletteMode;
  toggle: () => void;
}

const ColorModeContext = createContext<ColorMode>({ mode: "light", toggle: () => {} });

export const useColorMode = () => useContext(ColorModeContext);

function storedChoice(): PaletteMode | null {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

export function ColorModeProvider({ children }: { children: ReactNode }) {
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");
  const [choice, setChoice] = useState<PaletteMode | null>(storedChoice);
  const mode: PaletteMode = choice ?? (prefersDark ? "dark" : "light");

  useEffect(() => {
    document.documentElement.classList.toggle("theme-dark", mode === "dark");
    document.documentElement.classList.toggle("theme-light", mode === "light");
  }, [mode]);

  const value = useMemo<ColorMode>(
    () => ({
      mode,
      toggle: () => {
        const next = mode === "dark" ? "light" : "dark";
        setChoice(next);
        try {
          localStorage.setItem(KEY, next);
        } catch {
          // private mode: the choice lasts this session
        }
      },
    }),
    [mode],
  );
  const theme = useMemo(() => createTheme(themeSettings(mode)), [mode]);

  return (
    <ColorModeContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ColorModeContext.Provider>
  );
}
