export interface ManPage {
  slug: string;
  title: string;
  content: string;
}

export interface ManPageGroup {
  label: string;
  pages: ManPage[];
}

// Import man pages from project root via Vite's ?raw suffix
import jurisMain from "../../../man/juris.md?raw";
import man from "../../../man/man.md?raw";
import collect from "../../../man/collect.md?raw";
import collectType from "../../../man/collect-type.md?raw";
import collectAll from "../../../man/collect-all.md?raw";
import status from "../../../man/status.md?raw";
import stats from "../../../man/stats.md?raw";

export const manPageGroups: ManPageGroup[] = [
  {
    label: "Overview",
    pages: [
      { slug: "juris", title: "zig", content: jurisMain },
      { slug: "man", title: "zig man", content: man },
    ],
  },
  {
    label: "Collection",
    pages: [
      { slug: "collect", title: "zig collect", content: collect },
      { slug: "collect-type", title: "zig collect-type", content: collectType },
      { slug: "collect-all", title: "zig collect-all", content: collectAll },
    ],
  },
  {
    label: "Inspection",
    pages: [
      { slug: "status", title: "zig status", content: status },
      { slug: "stats", title: "zig stats", content: stats },
    ],
  },
];

export const manPages: ManPage[] = manPageGroups.flatMap((group) => group.pages);

export function getManPageBySlug(slug: string): ManPage | undefined {
  return manPages.find((page) => page.slug === slug);
}
