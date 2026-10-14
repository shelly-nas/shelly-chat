// What still stands between the user and a first answer, shown on an empty
// conversation. Each line says what is wrong and what to do about it.
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import { Box, Button, Card, CardContent, Stack, Typography } from "@mui/material";

import { useNavigate } from "react-router-dom";

import { useAppState } from "../appState";
import { hasModel } from "../lib/ollama";
import type { DocIndex } from "../lib/types";

interface Check {
  ok: boolean;
  label: string;
  hint: string;
  /** Only needed for sources; without it the model still answers. */
  optional?: boolean;
}

export function useChecks(selected: DocIndex | null): Check[] | null {
  const { config, configError, ollama, llmModel } = useAppState();
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
  ];
  // Without an index (or an empty one) the model answers without sources.
  if (selected) {
    checks.push({
      ok: selected.documents > 0,
      label: selected.documents > 0 ? `${selected.documents} documenten in “${selected.name}”` : `“${selected.name}” is nog leeg`,
      hint: "Antwoorden komen zonder bronnen tot je de index vult: open hem onder Indexen en klik op Index bijwerken.",
      optional: true,
    });
  }
  if (selected && ollama.status === "ok" && config?.embed_model) {
    const ok = hasModel(models, config.embed_model);
    checks.push({
      ok,
      label: ok ? `${config.embed_model} is geïnstalleerd` : `${config.embed_model} ontbreekt`,
      hint: `Nodig om in de index te zoeken; zonder komen antwoorden zonder bronnen. ollama pull ${config.embed_model}`,
      optional: true,
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

export default function Readiness({ index }: { index: DocIndex | null }) {
  const checks = useChecks(index);
  const navigate = useNavigate();
  if (!checks || checks.every((c) => c.ok)) return null;
  const blocked = checks.some((c) => !c.ok && !c.optional);

  return (
    <Card sx={{ width: "100%" }}>
      <CardContent sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <Box>
          <Typography variant="h3" component="h2">{blocked ? "Nog niet klaar voor vragen" : "Vragen kan, maar zonder bronnen"}</Typography>
          <Typography variant="body2" sx={{ mt: 2 }}>
            {blocked
              ? "Je gesprekken staan veilig op de NAS; alleen het beantwoorden wacht hierop."
              : "Het taalmodel antwoordt, maar kan nog niet in je documenten zoeken."}
          </Typography>
        </Box>
        <Stack spacing={3} component="ul" sx={{ m: 0, p: 0, listStyle: "none" }}>
          {checks.map((c) => (
            <Stack key={c.label} component="li" direction="row" spacing={3} alignItems="flex-start">
              {c.ok ? (
                <CheckCircleOutlineIcon fontSize="small" color="success" aria-hidden sx={{ mt: 0.5 }} />
              ) : (
                <ErrorOutlineIcon fontSize="small" color={c.optional ? "warning" : "error"} aria-hidden sx={{ mt: 0.5 }} />
              )}
              <Box>
                <Typography sx={{ fontSize: 14, fontWeight: 600, color: "text.primary" }}>{c.label}</Typography>
                {!c.ok && <Typography variant="body2">{c.hint}</Typography>}
              </Box>
            </Stack>
          ))}
        </Stack>
        <Box>
          <Button variant="outlined" onClick={() => navigate("/instellingen")}>
            Instellingen openen
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}
