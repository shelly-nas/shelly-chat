// GitLab, read from the browser with the user's own token.
//
// The browser runs on the machine that can reach GitLab (on the VPN, if
// needed); the NAS often cannot. GitLab's REST API allows cross-origin calls
// with a PRIVATE-TOKEN header. Mirrors host/indexing/gitlab_*_fetcher.py.

export const SUPPORTED_EXTENSIONS = [".md", ".adoc", ".pdf", ".docx", ".doc"];

export class GitLabError extends Error {}

/** One document to index; `load` fetches its content when it is its turn. */
export interface SourceItem {
  file_path: string;
  file_name: string;
  source_url: string;
  metadata: Record<string, string>;
  load: (signal?: AbortSignal) => Promise<{ text?: string; data_base64?: string }>;
}

export function parseWikiUrl(url: string): { base: string; project: string } {
  const trimmed = url.replace(/\/+$/, "").replace(/\/-\/wikis.*$/, "");
  const m = trimmed.match(/^(https?:\/\/[^/]+)\/(.+)$/);
  if (!m) throw new GitLabError(`Kan de wiki-URL niet lezen: ${url}`);
  return { base: m[1], project: m[2].replace(/\/+$/, "") };
}

export function parseRepoUrl(url: string): { base: string; project: string; branch?: string; path?: string } {
  const clean = url.replace(/\/+$/, "").split("?")[0];
  const tree = clean.match(/\/-\/tree\/([^/]+)(?:\/(.+))?$/);
  const basePart = tree ? clean.slice(0, tree.index) : clean.replace(/\/-\/(tree|blob).*$/, "");
  const m = basePart.match(/^(https?:\/\/[^/]+)\/(.+)$/);
  if (!m) throw new GitLabError(`Kan de repository-URL niet lezen: ${url}`);
  return { base: m[1], project: m[2].replace(/\/+$/, ""), branch: tree?.[1], path: tree?.[2] };
}

export function extensionOf(path: string): string {
  const name = path.split("/").pop() ?? "";
  return name.includes(".") ? `.${name.split(".").pop()!.toLowerCase()}` : "";
}

async function get(url: string, token: string, signal?: AbortSignal): Promise<any> {
  let res: Response;
  try {
    res = await fetch(url, { headers: token ? { "PRIVATE-TOKEN": token } : {}, signal });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new GitLabError(
      `GitLab is niet bereikbaar (${new URL(url).host}). Staat de VPN aan?`,
    );
  }
  if (res.status === 401) throw new GitLabError("GitLab weigert het token. Controleer je GitLab-token.");
  if (res.status === 403) throw new GitLabError("Het GitLab-token mag dit project niet lezen (read_api nodig).");
  if (res.status === 404) throw new GitLabError(`Niet gevonden in GitLab: ${url.split("/api/v4/")[1] ?? url}`);
  if (!res.ok) throw new GitLabError(`GitLab gaf ${res.status} op ${url}`);
  return res.json();
}

/** All pages of a list endpoint; stops at the first short page. */
async function getAll(url: string, token: string, signal?: AbortSignal): Promise<any[]> {
  const perPage = 100;
  const items: any[] = [];
  for (let page = 1; ; page++) {
    const sep = url.includes("?") ? "&" : "?";
    const batch: any[] = await get(`${url}${sep}per_page=${perPage}&page=${page}`, token, signal);
    items.push(...batch);
    if (batch.length < perPage) return items;
  }
}

export async function listWiki(url: string, token: string, signal?: AbortSignal): Promise<SourceItem[]> {
  const { base, project } = parseWikiUrl(url);
  const api = `${base}/api/v4/projects/${encodeURIComponent(project)}`;
  const pages = await getAll(`${api}/wikis?with_content=1`, token, signal);
  return pages
    .filter((p) => (p.format ?? "markdown") === "markdown" || p.format === "md")
    .filter((p) => (p.content ?? "").trim())
    .map((p) => {
      const sourceUrl = `${base}/${project}/-/wikis/${p.slug}`;
      return {
        file_path: sourceUrl,
        file_name: `${p.slug}.md`,
        source_url: sourceUrl,
        metadata: { wiki_project: project, wiki_slug: p.slug, title: p.title ?? p.slug },
        load: async () => ({ text: p.content as string }),
      };
    });
}

export async function listRepo(url: string, token: string, signal?: AbortSignal): Promise<SourceItem[]> {
  const parsed = parseRepoUrl(url);
  const api = `${parsed.base}/api/v4/projects/${encodeURIComponent(parsed.project)}`;
  const branch = parsed.branch ?? (await get(api, token, signal)).default_branch ?? "main";
  const pathParam = parsed.path ? `&path=${encodeURIComponent(parsed.path.replace(/\/+$/, ""))}` : "";
  const tree = await getAll(
    `${api}/repository/tree?recursive=true&ref=${encodeURIComponent(branch)}${pathParam}`,
    token,
    signal,
  );
  return tree
    .filter((t) => t.type === "blob" && SUPPORTED_EXTENSIONS.includes(extensionOf(t.path)))
    .map((t) => {
      const sourceUrl = `${parsed.base}/${parsed.project}/-/blob/${branch}/${t.path}`;
      return {
        file_path: sourceUrl,
        file_name: t.path.split("/").pop(),
        source_url: sourceUrl,
        metadata: { repo_project: parsed.project, repo_branch: branch, repo_file_path: t.path },
        // The NAS decodes the bytes: text for Markdown, extraction for PDF/DOCX.
        load: async (sig?: AbortSignal) => {
          const file = await get(
            `${api}/repository/files/${encodeURIComponent(t.path)}?ref=${encodeURIComponent(branch)}`,
            token,
            sig,
          );
          return { data_base64: file.content as string };
        },
      };
    });
}
