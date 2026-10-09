// How to let this page talk to Ollama: Ollama only answers browsers on origins
// it trusts, and this app runs on the NAS's origin, not on localhost.
import { Box, Typography } from "@mui/material";

function Code({ children }: { children: string }) {
  return (
    <Box
      component="pre"
      sx={{
        m: 0,
        p: 3,
        borderRadius: 2,
        bgcolor: "action.hover",
        fontSize: 13,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        overflowX: "auto",
        whiteSpace: "pre",
      }}
    >
      {children}
    </Box>
  );
}

export default function OllamaHelp({ ollamaUrl }: { ollamaUrl: string }) {
  const origin = window.location.origin;
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Typography variant="body2">
        Deze pagina praat rechtstreeks met Ollama op <strong>{ollamaUrl}</strong>. Controleer dat Ollama
        draait en dat het verzoeken van <strong>{origin}</strong> toestaat:
      </Typography>
      <Typography variant="overline" component="p">macOS</Typography>
      <Code>{`launchctl setenv OLLAMA_ORIGINS "${origin}"\n# daarna Ollama afsluiten en opnieuw openen`}</Code>
      <Typography variant="overline" component="p">Linux (systemd)</Typography>
      <Code>{`sudo systemctl edit ollama\n# [Service]\n# Environment="OLLAMA_ORIGINS=${origin}"\nsudo systemctl restart ollama`}</Code>
      <Typography variant="overline" component="p">Windows</Typography>
      <Code>{`setx OLLAMA_ORIGINS "${origin}"\n# daarna Ollama afsluiten en opnieuw openen`}</Code>
      <Typography variant="body2">
        Vraagt de browser om toegang tot apparaten in je lokale netwerk? Sta dat toe: zo mag deze pagina
        Ollama op je eigen computer bereiken.
      </Typography>
    </Box>
  );
}
