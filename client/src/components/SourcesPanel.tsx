// The sources of one answer, one at a time, with a link to the original document.
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { Box, Button, Chip, IconButton, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";

import type { SourceContext } from "../lib/types";

function fileName(path: string): string {
  return decodeURIComponent(path.split("/").pop() || path);
}

export default function SourcesPanel({ sources }: { sources: SourceContext[] }) {
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(0), [sources]);

  if (sources.length === 0) {
    return (
      <Box sx={{ p: 6 }}>
        <Typography variant="h3" component="h2">Bronnen</Typography>
        <Typography variant="body2" sx={{ mt: 2 }}>
          Na je vraag staan hier de stukken uit de documenten waarop het antwoord gebaseerd is.
        </Typography>
      </Box>
    );
  }

  const source = sources[Math.min(index, sources.length - 1)];
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <Box sx={{ p: 6, pb: 4, borderBottom: 1, borderColor: "divider" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="h3" component="h2">
            Bronnen
          </Typography>
          <Stack direction="row" alignItems="center" spacing={1}>
            <IconButton aria-label="Vorige bron" disabled={index === 0} onClick={() => setIndex((i) => i - 1)}>
              <ChevronLeftIcon />
            </IconButton>
            <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums", minWidth: 40, textAlign: "center" }}>
              {index + 1} / {sources.length}
            </Typography>
            <IconButton
              aria-label="Volgende bron"
              disabled={index >= sources.length - 1}
              onClick={() => setIndex((i) => i + 1)}
            >
              <ChevronRightIcon />
            </IconButton>
          </Stack>
        </Stack>
        <Typography sx={{ mt: 3, fontSize: 14, fontWeight: 600, color: "text.primary", overflowWrap: "anywhere" }}>
          [{source.source_num}] {fileName(source.file_path)}
        </Typography>
        {source.section_context && (
          <Typography variant="body2" sx={{ mt: 1, overflowWrap: "anywhere" }}>
            {source.section_context}
          </Typography>
        )}
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
          <Chip
            size="small"
            label={`Relevantie ${Math.round(Math.max(0, Math.min(1, source.similarity)) * 100)}%`}
            sx={{ bgcolor: "action.hover", color: "text.secondary" }}
          />
          <Chip
            size="small"
            label={source.chunk_type === "parent" ? "Hele sectie" : "Fragment"}
            sx={{ bgcolor: "action.hover", color: "text.secondary" }}
          />
          {source.source_url && (
            <Button
              size="small"
              variant="text"
              endIcon={<OpenInNewIcon sx={{ fontSize: 16 }} />}
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Openen
            </Button>
          )}
        </Stack>
      </Box>
      <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto", p: 6 }}>
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", color: "text.primary" }}>
          {source.content}
        </Typography>
      </Box>
    </Box>
  );
}
