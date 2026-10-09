import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import { Alert, AlertTitle, Box, Button, Chip, CircularProgress, Stack, Typography } from "@mui/material";

import { STAGE_LABEL, type Stage } from "../lib/rag";
import type { ChatMessage } from "../lib/types";
import ExpansionNote from "./ExpansionNote";
import Markdown from "./Markdown";

export interface ViewMessage extends ChatMessage {
  pending?: boolean;
  stopped?: boolean;
  error?: { title: string; detail: string; ollama: boolean };
}

interface Props {
  message: ViewMessage;
  stage: Stage | null;
  sourcesSelected: boolean;
  onShowSources: () => void;
  onRetry: () => void;
  onHelp: () => void;
}

function formatDuration(ms: number): string {
  return ms < 10_000 ? `${(ms / 1000).toFixed(1).replace(".", ",")} s` : `${Math.round(ms / 1000)} s`;
}

export default function MessageView({ message, stage, sourcesSelected, onShowSources, onRetry, onHelp }: Props) {
  if (message.role === "user") {
    return (
      <Stack spacing={1} sx={{ alignItems: "flex-end" }}>
        <Box
          sx={{
            maxWidth: "85%",
            px: 4,
            py: 3,
            borderRadius: 3,
            borderBottomRightRadius: 4,
            bgcolor: "action.selected",
            color: "text.primary",
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
            fontSize: 16,
            lineHeight: 1.5,
          }}
        >
          {message.content}
        </Box>
        {message.expansions && <ExpansionNote expansions={message.expansions} />}
      </Stack>
    );
  }

  if (message.error) {
    return (
      <Alert
        severity="error"
        action={
          <Stack direction="row" spacing={1} sx={{ alignSelf: "center" }}>
            {message.error.ollama && (
              <Button size="small" variant="text" onClick={onHelp}>
                Hoe los ik dit op?
              </Button>
            )}
            <Button size="small" variant="outlined" onClick={onRetry}>
              Opnieuw proberen
            </Button>
          </Stack>
        }
      >
        <AlertTitle sx={{ fontWeight: 600 }}>{message.error.title}</AlertTitle>
        {message.error.detail}
      </Alert>
    );
  }

  const sources = message.sources ?? [];
  return (
    <Box>
      {message.pending && !message.content ? (
        <Stack direction="row" spacing={3} alignItems="center" sx={{ py: 2 }} role="status">
          <CircularProgress size={16} thickness={5} />
          <Typography variant="body2">{stage ? STAGE_LABEL[stage] : "Bezig…"}</Typography>
        </Stack>
      ) : (
        <Markdown>{message.content}</Markdown>
      )}
      {!message.pending && (
        <Stack direction="row" spacing={3} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 3 }}>
          {sources.length > 0 && (
            <Chip
              icon={<ArticleOutlinedIcon aria-hidden />}
              label={`${sources.length} ${sources.length === 1 ? "bron" : "bronnen"}`}
              onClick={onShowSources}
              color={sourcesSelected ? "primary" : "default"}
              variant={sourcesSelected ? "filled" : "outlined"}
              sx={{ height: 32, minHeight: 32 }}
            />
          )}
          {(message.model || message.duration_ms) && (
            <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums" }}>
              {[message.model, message.duration_ms ? formatDuration(message.duration_ms) : null]
                .filter(Boolean)
                .join(" · ")}
            </Typography>
          )}
          {message.stopped && <Typography variant="caption">Gestopt, niet opgeslagen</Typography>}
        </Stack>
      )}
      {!message.pending && sources.length > 0 && (
        <Typography variant="caption" component="p" sx={{ mt: 2 }}>
          Controleer belangrijke informatie in de originele brondocumenten.
        </Typography>
      )}
    </Box>
  );
}
