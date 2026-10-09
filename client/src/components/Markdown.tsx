import { Box, Link } from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Assistant answers are Markdown. Styled with theme values so they follow
// light and dark mode.
export default function Markdown({ children }: { children: string }) {
  return (
    <Box
      sx={{
        color: "text.primary",
        fontSize: 16,
        lineHeight: 1.5,
        overflowWrap: "anywhere",
        "& > :first-of-type": { mt: 0 },
        "& > :last-child": { mb: 0 },
        "& p": { my: 3 },
        "& ul, & ol": { my: 3, pl: 6 },
        "& li": { my: 1 },
        "& h1, & h2, & h3, & h4": { fontSize: 18, fontWeight: 600, mt: 6, mb: 2, lineHeight: 1.3 },
        "& blockquote": { m: 0, my: 3, pl: 4, borderLeft: 3, borderColor: "divider", color: "text.secondary" },
        "& code": {
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: 14,
          px: 1,
          py: 0.5,
          borderRadius: 1.5,
          bgcolor: "action.hover",
        },
        "& pre": { my: 3, p: 4, borderRadius: 2, bgcolor: "action.hover", overflowX: "auto" },
        "& pre code": { p: 0, bgcolor: "transparent" },
        "& table": { borderCollapse: "collapse", my: 3, display: "block", overflowX: "auto" },
        "& th, & td": { border: 1, borderColor: "divider", px: 3, py: 2, fontSize: 14, textAlign: "left" },
        "& th": { fontWeight: 600 },
        "& hr": { border: 0, borderTop: 1, borderColor: "divider", my: 6 },
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <Link href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </Link>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </Box>
  );
}
