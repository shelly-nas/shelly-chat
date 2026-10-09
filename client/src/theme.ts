// shelly-nas MUI theme - the Web App Template expressed as MUI theme options.
// Values mirror tokens.css; change them there and here together.
//
// Usage:
//   import "@fontsource/figtree/400.css"; // and 500, 600, 700
//   const theme = createTheme(themeSettings(mode));
//
// Type mapping: h1 = Display, h2 = Title, h3 = Heading, body1 = Body,
// body2 = Small, overline = Label.
import { PaletteMode } from "@mui/material";
import { ThemeOptions } from "@mui/material/styles";

const light = {
  bg: "#F8F9FB",
  surface: "#FFFFFF",
  surface2: "#F2F4F7",
  surface3: "#E6E9EF",
  border: "#E1E5EB",
  borderStrong: "#C9D0DA",
  text: "#12161C",
  textBody: "#343B48",
  textMuted: "#5F6878",
  textDisabled: "#8A93A3",
  primary: "#1F4FC4",
  primaryHover: "#1B3F9C",
  primaryActive: "#1A3477",
  primarySoft: "#EEF4FF",
  primarySoft2: "#DCE7FE",
  onPrimary: "#FFFFFF",
  focus: "#2F64E0",
  success: "#1A7F4B",
  successSoft: "#E7F6EE",
  warning: "#9A5200",
  warningSoft: "#FFF4DB",
  error: "#C8322B",
  errorSoft: "#FDECEB",
  shadow1: "0 1px 2px rgba(18,22,28,.06), 0 1px 3px rgba(18,22,28,.08)",
  shadow2: "0 8px 24px rgba(18,22,28,.12)",
};

const dark: typeof light = {
  bg: "#0F1217",
  surface: "#171B22",
  surface2: "#1F242D",
  surface3: "#282E39",
  border: "#2A303B",
  borderStrong: "#3A4250",
  text: "#EEF0F4",
  textBody: "#C9CFD9",
  textMuted: "#9AA3B2",
  textDisabled: "#646D7C",
  primary: "#7EA2F0",
  primaryHover: "#98B5F4",
  primaryActive: "#B1C7F7",
  primarySoft: "#1C2742",
  primarySoft2: "#24335A",
  onPrimary: "#0F1217",
  focus: "#98B5F4",
  success: "#5BC48A",
  successSoft: "#14291E",
  warning: "#E9B85A",
  warningSoft: "#2E2412",
  error: "#F0817A",
  errorSoft: "#33191A",
  // Shadows disappear on dark grounds; elevation comes from lighter surfaces.
  shadow1: "none",
  shadow2: "none",
};

export const tokensFor = (mode: PaletteMode) => (mode === "dark" ? dark : light);

const fontFamily = ["Figtree", "system-ui", "-apple-system", "Segoe UI", "sans-serif"].join(",");

export const themeSettings = (mode: PaletteMode = "light"): ThemeOptions => {
  const t = tokensFor(mode);
  const focusRing = `0 0 0 2px ${t.surface}, 0 0 0 4px ${t.focus}`;

  return {
    palette: {
      mode,
      primary: { main: t.primary, dark: t.primaryActive, light: t.primarySoft2, contrastText: t.onPrimary },
      success: { main: t.success, light: t.successSoft, contrastText: t.onPrimary },
      warning: { main: t.warning, light: t.warningSoft, contrastText: t.onPrimary },
      error: { main: t.error, light: t.errorSoft, contrastText: t.onPrimary },
      info: { main: t.primary, light: t.primarySoft, contrastText: t.onPrimary },
      background: { default: t.bg, paper: t.surface },
      text: { primary: t.text, secondary: t.textMuted, disabled: t.textDisabled },
      divider: t.border,
      action: { hover: t.surface2, selected: t.primarySoft, disabledBackground: t.surface3, disabled: t.textDisabled },
    },
    // MUI multiplies this: theme.spacing(1) = 4px, spacing(4) = 16px, spacing(8) = 32px.
    spacing: 4,
    shape: { borderRadius: 8 },
    typography: {
      fontFamily,
      fontSize: 14,
      h1: { fontSize: 32, fontWeight: 700, lineHeight: 1.15, letterSpacing: "-0.025em", color: t.text },
      h2: { fontSize: 24, fontWeight: 600, lineHeight: 1.2, letterSpacing: "-0.02em", color: t.text },
      h3: { fontSize: 20, fontWeight: 600, lineHeight: 1.25, letterSpacing: "-0.015em", color: t.text },
      body1: { fontSize: 16, lineHeight: 1.5, color: t.textBody },
      body2: { fontSize: 14, lineHeight: 1.5, color: t.textMuted },
      overline: { fontSize: 12, fontWeight: 600, lineHeight: 1.35, letterSpacing: "0.06em", textTransform: "uppercase", color: t.textMuted },
      caption: { fontSize: 12, lineHeight: 1.4, color: t.textMuted },
      button: { fontSize: 14, fontWeight: 600, textTransform: "none", lineHeight: 1 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: { body: { WebkitFontSmoothing: "antialiased" } },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: {
            height: 40,
            padding: "0 16px",
            borderRadius: 8,
            gap: 8,
            whiteSpace: "nowrap",
            transition: "background-color .15s ease, border-color .15s ease, color .15s ease, box-shadow .15s ease, transform .05s ease",
            "&:active": { transform: "translateY(1px)" },
            "&.Mui-focusVisible": { boxShadow: focusRing },
            "&.Mui-disabled": { background: t.surface3, borderColor: "transparent", color: t.textDisabled },
          },
          sizeSmall: { height: 32, padding: "0 12px", borderRadius: 6 },
          sizeLarge: { height: 48, padding: "0 24px", fontSize: 16 },
          // Primary = <Button variant="contained">
          containedPrimary: {
            "&:hover": { background: t.primaryHover },
            "&:active": { background: t.primaryActive },
          },
          // Secondary = <Button variant="outlined">
          outlined: {
            borderColor: t.borderStrong,
            "&:hover": { background: t.primarySoft, borderColor: t.primarySoft2 },
            "&:active": { background: t.primarySoft2 },
          },
          // Quiet = <Button variant="text">, in body color
          text: {
            color: t.textBody,
            "&:hover": { background: t.surface2, color: t.text },
            "&:active": { background: t.surface3 },
          },
          // Destructive = <Button variant="outlined" color="error">
          outlinedError: {
            color: t.error,
            borderColor: t.borderStrong,
            "&:hover": { background: t.errorSoft, borderColor: t.error },
          },
        },
      },
      MuiIconButton: {
        styleOverrides: { root: { borderRadius: 8, "&.Mui-focusVisible": { boxShadow: focusRing } } },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            background: t.surface,
            fontSize: 16,
            "& .MuiOutlinedInput-notchedOutline": { borderColor: t.borderStrong },
            "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: t.textDisabled },
            "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: t.focus, borderWidth: 1 },
            "&.Mui-focused": { boxShadow: `0 0 0 3px ${t.primarySoft2}` },
            "&.Mui-error .MuiOutlinedInput-notchedOutline": { borderColor: t.error },
            "&.Mui-error.Mui-focused": { boxShadow: `0 0 0 3px ${t.errorSoft}` },
            "&.Mui-disabled": { background: t.surface2 },
          },
          input: { height: 40, padding: "0 12px", boxSizing: "border-box" },
          multiline: { padding: "8px 12px" },
        },
      },
      // Label above the field, never floating inside it.
      MuiInputLabel: {
        defaultProps: { shrink: true },
        styleOverrides: {
          root: { position: "relative", transform: "none", marginBottom: 8, fontSize: 14, fontWeight: 600, color: t.text },
        },
      },
      MuiFormHelperText: { styleOverrides: { root: { marginLeft: 0, marginTop: 8, fontSize: 12 } } },
      MuiCard: {
        defaultProps: { elevation: 0 },
        styleOverrides: { root: { borderRadius: 12, border: `1px solid ${t.border}`, boxShadow: t.shadow1, backgroundImage: "none" } },
      },
      MuiCardContent: { styleOverrides: { root: { padding: 24, "&:last-child": { paddingBottom: 24 } } } },
      MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
      MuiMenu: { styleOverrides: { paper: { borderRadius: 8, boxShadow: t.shadow2, border: `1px solid ${t.border}`, background: t.surface2 } } },
      MuiDialog: { styleOverrides: { paper: { borderRadius: 12 } } },
      MuiChip: {
        // Status badges: <Chip size="small" color="success" label="Paid" />
        styleOverrides: { root: { height: 24, borderRadius: 999, fontSize: 12, fontWeight: 600 } },
      },
      MuiAlert: {
        styleOverrides: {
          root: { borderRadius: 8, padding: "12px 16px", fontSize: 14, color: t.textBody },
          standardInfo: { background: t.primarySoft },
          standardSuccess: { background: t.successSoft },
          standardWarning: { background: t.warningSoft },
          standardError: { background: t.errorSoft },
        },
      },
      MuiTabs: {
        styleOverrides: {
          root: { minHeight: 44, borderBottom: `1px solid ${t.border}` },
          indicator: { height: 2, borderRadius: 2, background: t.primary },
        },
      },
      MuiTab: {
        styleOverrides: {
          root: {
            minHeight: 44, minWidth: 0, padding: 0, marginRight: 24,
            textTransform: "none", fontSize: 14, fontWeight: 500, color: t.textMuted,
            "&:hover": { color: t.text },
            "&.Mui-selected": { color: t.text, fontWeight: 600 },
          },
        },
      },
      MuiSwitch: {
        styleOverrides: {
          root: { width: 40, height: 24, padding: 0 },
          switchBase: {
            padding: 3,
            "&.Mui-checked": { transform: "translateX(16px)", color: "#FFFFFF" },
            "&.Mui-checked + .MuiSwitch-track": { background: t.primary, opacity: 1 },
          },
          thumb: { width: 18, height: 18, boxShadow: "0 1px 2px rgba(0,0,0,.2)" },
          track: { borderRadius: 999, background: t.borderStrong, opacity: 1 },
        },
      },
      MuiListItemButton: {
        // Sidebar navigation items
        styleOverrides: {
          root: {
            height: 40, borderRadius: 8, padding: "0 12px", gap: 12, fontSize: 14, fontWeight: 500, color: t.textBody,
            "&:hover": { background: t.surface2, color: t.text },
            "&.Mui-selected": { background: t.primarySoft, color: t.primary, fontWeight: 600 },
            "&.Mui-selected:hover": { background: t.primarySoft },
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: { padding: "12px 24px", borderBottom: `1px solid ${t.border}`, fontSize: 14, color: t.textBody, whiteSpace: "nowrap" },
          head: { fontSize: 12, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: t.textMuted },
        },
      },
      MuiTableRow: { styleOverrides: { root: { "&:hover": { background: t.surface2 } } } },
      MuiSnackbarContent: {
        styleOverrides: {
          root: mode === "dark"
            ? { borderRadius: 12, background: t.surface3, color: t.text, border: `1px solid ${t.borderStrong}`, boxShadow: "none" }
            : { borderRadius: 12, background: "#12161C", color: "#F2F4F7", boxShadow: "0 8px 24px rgba(18,22,28,.24)" },
        },
      },
      MuiSkeleton: { styleOverrides: { root: { borderRadius: 6, background: t.surface2 } } },
      MuiAvatar: { styleOverrides: { root: { background: t.primarySoft2, color: t.primary, fontWeight: 700 } } },
    },
  };
};
