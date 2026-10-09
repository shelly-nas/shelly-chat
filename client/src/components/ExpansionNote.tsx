// Shows which abbreviations in the question were written out, and where each
// definition was found.
import AutoFixHighOutlinedIcon from "@mui/icons-material/AutoFixHighOutlined";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { Box, ButtonBase, Collapse, Link, Stack, Typography } from "@mui/material";
import { useState } from "react";

import type { ExpansionSource } from "../lib/types";

export default function ExpansionNote({ expansions }: { expansions: ExpansionSource[] }) {
  const [open, setOpen] = useState(false);
  if (expansions.length === 0) return null;

  const grouped = new Map<string, ExpansionSource[]>();
  for (const e of expansions) grouped.set(e.abbrev, [...(grouped.get(e.abbrev) ?? []), e]);

  return (
    <Box sx={{ maxWidth: "85%", display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
      <ButtonBase
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        sx={{
          gap: 2,
          px: 3,
          minHeight: 32,
          borderRadius: 1.5,
          color: "text.secondary",
          fontSize: 12,
          "&:hover": { bgcolor: "action.hover", color: "text.primary" },
          "&.Mui-focusVisible": { outline: 2, outlineColor: "primary.main" },
        }}
      >
        <AutoFixHighOutlinedIcon sx={{ fontSize: 16 }} aria-hidden />
        <span>
          Afkortingen uitgeschreven: <strong>{[...grouped.keys()].join(", ")}</strong>
        </span>
        {open ? <ExpandLessIcon sx={{ fontSize: 16 }} /> : <ExpandMoreIcon sx={{ fontSize: 16 }} />}
      </ButtonBase>
      <Collapse in={open}>
        <Stack spacing={3} sx={{ mt: 1, p: 4, borderRadius: 2, border: 1, borderColor: "divider", bgcolor: "background.paper" }}>
          {[...grouped.entries()].map(([abbrev, entries]) => (
            <Box key={abbrev}>
              <Typography sx={{ fontSize: 14, fontWeight: 600, color: "text.primary" }}>
                {abbrev} → {entries[0].term}
              </Typography>
              {entries.map((e, i) => (
                <Box key={i} sx={{ mt: 1, pl: 3, borderLeft: 2, borderColor: "divider" }}>
                  <Link href={e.source_url} target="_blank" rel="noopener noreferrer" sx={{ fontSize: 12 }}>
                    {e.file_name || e.source_url}
                  </Link>
                  <Typography variant="caption" component="p" sx={{ fontStyle: "italic" }}>
                    {e.snippet}
                  </Typography>
                </Box>
              ))}
            </Box>
          ))}
        </Stack>
      </Collapse>
    </Box>
  );
}
