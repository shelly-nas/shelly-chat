// App shell from design-richtlijnen/patterns.md: a 248px sidebar with the app,
// the conversations and the user's tools; on narrow screens a top bar with a
// menu instead.
import AddIcon from "@mui/icons-material/Add";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import MenuIcon from "@mui/icons-material/Menu";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import {
  Alert,
  Avatar,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Skeleton,
  Snackbar,
  Stack,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { useState, type ReactNode } from "react";
import { useMatch, useNavigate } from "react-router-dom";

import { useAppState } from "../appState";
import { useColorMode } from "../colorMode";
import { api } from "../lib/api";
import type { ConversationSummary } from "../lib/types";
import OllamaStatus from "./OllamaStatus";
import SettingsDialog from "./SettingsDialog";

const SIDEBAR_WIDTH = 248;

function Brand() {
  return (
    <Stack direction="row" spacing={3} alignItems="center">
      <Avatar variant="rounded" sx={{ width: 32, height: 32, borderRadius: 2, bgcolor: "primary.main", color: "primary.contrastText" }}>
        <ChatBubbleOutlineIcon fontSize="small" aria-hidden />
      </Avatar>
      <Box sx={{ minWidth: 0 }}>
        <Typography sx={{ fontSize: 14, fontWeight: 700, color: "text.primary", lineHeight: 1.3 }}>
          Shelly Chat
        </Typography>
        <Typography variant="caption">Documentassistent</Typography>
      </Box>
    </Stack>
  );
}

function ConversationList({ onNavigate }: { onNavigate: () => void }) {
  const { conversations, conversationsError, refreshConversations } = useAppState();
  const navigate = useNavigate();
  const match = useMatch("/c/:id");
  const [toDelete, setToDelete] = useState<ConversationSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const confirmDelete = async () => {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await api.deleteConversation(toDelete.id);
      if (match?.params.id === toDelete.id) navigate("/");
      await refreshConversations();
      setToast("Gesprek verwijderd");
    } catch (err) {
      setToast(`Verwijderen mislukt: ${(err as Error).message}`);
    } finally {
      setDeleting(false);
      setToDelete(null);
    }
  };

  if (conversationsError) {
    return (
      <Alert severity="error" action={<Button size="small" onClick={refreshConversations}>Opnieuw</Button>}>
        Gesprekken laden mislukt.
      </Alert>
    );
  }
  if (conversations === null) {
    return (
      <Stack spacing={2}>
        {[0, 1, 2].map((i) => <Skeleton key={i} variant="rounded" height={40} />)}
      </Stack>
    );
  }
  if (conversations.length === 0) {
    return (
      <Typography variant="body2" sx={{ px: 3 }}>
        Nog geen gesprekken. Je vragen en antwoorden komen hier te staan.
      </Typography>
    );
  }

  return (
    <>
      <List disablePadding sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {conversations.map((c) => (
          <ListItemButton
            key={c.id}
            selected={match?.params.id === c.id}
            onClick={() => {
              navigate(`/c/${c.id}`);
              onNavigate();
            }}
            sx={{ pr: 1, "& .delete": { opacity: 0 }, "&:hover .delete, &:focus-within .delete": { opacity: 1 } }}
          >
            <ListItemText
              primary={c.title}
              primaryTypographyProps={{ noWrap: true, fontSize: 14, fontWeight: "inherit", color: "inherit" }}
            />
            <IconButton
              className="delete"
              size="small"
              aria-label={`Gesprek "${c.title}" verwijderen`}
              onClick={(e) => {
                e.stopPropagation();
                setToDelete(c);
              }}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </ListItemButton>
        ))}
      </List>
      <Dialog open={toDelete !== null} onClose={() => !deleting && setToDelete(null)} maxWidth="xs" fullWidth>
        <DialogTitle variant="h3">Gesprek verwijderen?</DialogTitle>
        <DialogContent>
          <Typography variant="body1">
            “{toDelete?.title}” en alle antwoorden erin verdwijnen voorgoed van de NAS.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 6, pb: 6 }}>
          <Button variant="text" onClick={() => setToDelete(null)} disabled={deleting}>
            Annuleren
          </Button>
          <Button variant="outlined" color="error" onClick={confirmDelete} disabled={deleting}>
            {deleting ? "Verwijderen…" : "Verwijderen"}
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        open={toast !== null}
        autoHideDuration={2400}
        onClose={() => setToast(null)}
        message={toast}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </>
  );
}

function Sidebar({ onNavigate, onOpenSettings }: { onNavigate: () => void; onOpenSettings: () => void }) {
  const navigate = useNavigate();
  const { mode, toggle } = useColorMode();

  return (
    <Box
      component="nav"
      aria-label="Gesprekken"
      sx={{
        width: SIDEBAR_WIDTH,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        px: 4,
        py: 6,
        bgcolor: "background.paper",
        borderRight: 1,
        borderColor: "divider",
      }}
    >
      <Brand />
      <Button
        variant="outlined"
        startIcon={<AddIcon />}
        fullWidth
        onClick={() => {
          navigate("/");
          onNavigate();
        }}
      >
        Nieuw gesprek
      </Button>
      <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 2 }}>
        <Typography variant="overline" component="h2" sx={{ px: 3 }}>
          Gesprekken
        </Typography>
        <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto", mx: -1, px: 1 }}>
          <ConversationList onNavigate={onNavigate} />
        </Box>
      </Box>
      <Stack spacing={1}>
        <OllamaStatus onClick={onOpenSettings} />
        <Stack direction="row" alignItems="center" spacing={1}>
          <Button
            variant="text"
            startIcon={<SettingsOutlinedIcon fontSize="small" />}
            onClick={onOpenSettings}
            sx={{ flex: 1, justifyContent: "flex-start", px: 3 }}
          >
            Instellingen
          </Button>
          <Tooltip title={mode === "dark" ? "Lichte modus" : "Donkere modus"}>
          <IconButton aria-label={mode === "dark" ? "Lichte modus" : "Donkere modus"} onClick={toggle}>
            {mode === "dark" ? <LightModeOutlinedIcon fontSize="small" /> : <DarkModeOutlinedIcon fontSize="small" />}
          </IconButton>
          </Tooltip>
        </Stack>
      </Stack>
    </Box>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const theme = useTheme();
  const narrow = useMediaQuery(theme.breakpoints.down("md"));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { settingsOpen, setSettingsOpen } = useAppState();
  const openSettings = () => {
    setDrawerOpen(false);
    setSettingsOpen(true);
  };

  const sidebar = <Sidebar onNavigate={() => setDrawerOpen(false)} onOpenSettings={openSettings} />;

  return (
    <Box sx={{ display: "flex", height: "100dvh", bgcolor: "background.default" }}>
      {narrow ? (
        <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
          {sidebar}
        </Drawer>
      ) : (
        <Box sx={{ flex: `0 0 ${SIDEBAR_WIDTH}px` }}>{sidebar}</Box>
      )}
      <Box component="main" sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        {narrow && (
          <Stack
            direction="row"
            alignItems="center"
            spacing={2}
            sx={{ px: 2, height: 56, flexShrink: 0, borderBottom: 1, borderColor: "divider", bgcolor: "background.paper" }}
          >
            <IconButton aria-label="Menu openen" onClick={() => setDrawerOpen(true)} sx={{ width: 44, height: 44 }}>
              <MenuIcon />
            </IconButton>
            <Brand />
          </Stack>
        )}
        {children}
      </Box>
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </Box>
  );
}
