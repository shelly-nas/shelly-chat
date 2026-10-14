// Status of the user's own Ollama: a dot plus a word, never colour alone.
import { Box, ButtonBase, Typography } from "@mui/material";

import { useAppState } from "../appState";

export function StatusDot({ color }: { color: string }) {
  return <Box aria-hidden sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: color, flexShrink: 0 }} />;
}

export default function OllamaStatus({ onClick }: { onClick: () => void }) {
  const { ollama } = useAppState();
  const [color, label] =
    ollama.status === "ok"
      ? ["success.main", "Ollama verbonden"]
      : ollama.status === "checking"
        ? ["text.disabled", "Ollama controleren…"]
        : ["error.main", "Ollama niet bereikbaar"];

  return (
    <ButtonBase
      onClick={onClick}
      sx={{
        width: "100%",
        justifyContent: "flex-start",
        gap: 2,
        px: 3,
        minHeight: 40,
        borderRadius: 2,
        "&:hover": { bgcolor: "action.hover" },
        "&.Mui-focusVisible": { outline: 2, outlineColor: "primary.main" },
      }}
    >
      <StatusDot color={color} />
      <Typography noWrap sx={{ fontSize: 14, fontWeight: 500, color: "text.secondary" }}>
        {label}
      </Typography>
    </ButtonBase>
  );
}
