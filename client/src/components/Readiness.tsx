// What still stands between the user and a first answer, shown on an empty
// conversation. Each line says what is wrong and what to do about it.
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import { Box, Button, Card, CardContent, Stack, Typography } from "@mui/material";

import { useAppState } from "../appState";
import { hasModel } from "../lib/ollama";

interface Check {
  ok: boolean;
  label: string;
  hint: string;
}

export function useChecks(): Check[] | null {
  const { config, configError, index, ollama, llmModel } = useAppState();
  if (ollama.status === "checking" || (!config && !configError)) return null;

  const models = ollama.status === "ok" ? ollama.models : [];
  const checks: Check[] = [
    {
      ok: !configError,
      label: configError ? "De NAS reageert niet" : "De NAS is bereikbaar",
      hint: "Herlaad de pagina. Blijft dit zo, kijk dan of de containers van shelly-chat draaien.",
    },
    {
      ok: ollama.status === "ok",
      label: ollama.status === "ok" ? "Ollama is bereikbaar" : "Ollama is niet bereikbaar",
      hint: "Start Ollama en sta deze pagina toe met OLLAMA_ORIGINS. De instellingen leggen uit hoe.",
    },
    {
      ok: (index?.documents ?? 0) > 0,
      label: (index?.documents ?? 0) > 0 ? `${index!.documents} documenten geïndexeerd` : "Er is nog niets geïndexeerd",
      hint: "Open Index in de zijbalk om documenten uit GitLab te indexeren.",
    },
  ];
  if (ollama.status === "ok" && config?.embed_model) {
    const ok = hasModel(models, config.embed_model);
    checks.push({
      ok,
      label: ok ? `${config.embed_model} is geïnstalleerd` : `${config.embed_model} ontbreekt`,
      hint: `Nodig om je vraag te vergelijken met de index: ollama pull ${config.embed_model}`,
    });
  }
  if (ollama.status === "ok" && llmModel) {
    const ok = hasModel(models, llmModel);
    checks.push({
      ok,
      label: ok ? `${llmModel} is geïnstalleerd` : `${llmModel} ontbreekt`,
      hint: `Schrijft de antwoorden: ollama pull ${llmModel}, of kies een ander model in de instellingen.`,
    });
  }
  return checks;
}

export default function Readiness() {
  const checks = useChecks();
  const { setSettingsOpen } = useAppState();
  if (!checks || checks.every((c) => c.ok)) return null;

  return (
    <Card sx={{ width: "100%" }}>
      <CardContent sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <Box>
          <Typography variant="h3" component="h2">Nog niet klaar voor vragen</Typography>
          <Typography variant="body2" sx={{ mt: 2 }}>
            Je gesprekken staan veilig op de NAS; alleen het beantwoorden wacht hierop.
          </Typography>
        </Box>
        <Stack spacing={3} component="ul" sx={{ m: 0, p: 0, listStyle: "none" }}>
          {checks.map((c) => (
            <Stack key={c.label} component="li" direction="row" spacing={3} alignItems="flex-start">
              {c.ok ? (
                <CheckCircleOutlineIcon fontSize="small" color="success" aria-hidden sx={{ mt: 0.5 }} />
              ) : (
                <ErrorOutlineIcon fontSize="small" color="error" aria-hidden sx={{ mt: 0.5 }} />
              )}
              <Box>
                <Typography sx={{ fontSize: 14, fontWeight: 600, color: "text.primary" }}>{c.label}</Typography>
                {!c.ok && <Typography variant="body2">{c.hint}</Typography>}
              </Box>
            </Stack>
          ))}
        </Stack>
        <Box>
          <Button variant="outlined" onClick={() => setSettingsOpen(true)}>
            Instellingen openen
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}
