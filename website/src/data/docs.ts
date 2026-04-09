export interface DocPage {
  slug: string;
  title: string;
  content: string;
}

// Import docs from project root via Vite's ?raw suffix
import overview from "../../../docs/overview.md?raw";
import architecture from "../../../docs/architecture.md?raw";
import collectors from "../../../docs/collectors.md?raw";
import documentModel from "../../../docs/document-model.md?raw";
import storageFormat from "../../../docs/storage-format.md?raw";
import dataSources from "../../../docs/data-sources.md?raw";
import parsingRules from "../../../docs/parsing-rules.md?raw";

export const docs: DocPage[] = [
  { slug: "overview", title: "Overview", content: overview },
  { slug: "architecture", title: "Architecture", content: architecture },
  { slug: "collectors", title: "Collectors", content: collectors },
  { slug: "document-model", title: "Document Model", content: documentModel },
  { slug: "storage-format", title: "Storage Format", content: storageFormat },
  { slug: "data-sources", title: "Data Sources", content: dataSources },
  { slug: "parsing-rules", title: "Parsing Rules", content: parsingRules },
];

export function getDocBySlug(slug: string): DocPage | undefined {
  return docs.find((doc) => doc.slug === slug);
}
