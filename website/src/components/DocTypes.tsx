import { DOC_TYPES, DOC_TYPE_CATEGORIES } from "../data/sourceData";

const categoryIcons: Record<string, string> = {
  "Swedish Parliament": "\uD83C\uDFDB\uFE0F",
  "Swedish Government": "\uD83C\uDDF8\uD83C\uDDEA",
  "Courts": "\u2696\uFE0F",
  "Authorities": "\uD83D\uDCCB",
  "EU Law": "\uD83C\uDDEA\uD83C\uDDFA",
};

export default function DocTypes() {
  return (
    <section id="doc-types" className="border-t border-border py-20 md:py-28">
      <div className="mx-auto max-w-6xl px-6">
        <h2 className="text-center text-3xl font-bold text-text-primary md:text-4xl">
          {DOC_TYPES.length} document types across Swedish and EU law
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-text-secondary">
          Every document type is normalized into the same{" "}
          <code className="rounded bg-surface-alt px-1.5 py-0.5 text-xs text-accent">Document</code>{" "}
          schema with Pydantic validation, regardless of its source format.
        </p>

        <div className="mt-14 grid gap-8 md:grid-cols-2 lg:grid-cols-3">
          {Object.entries(DOC_TYPE_CATEGORIES).map(([category, docTypeValues]) => (
            <div key={category} className="rounded-xl border border-border bg-surface-alt p-6">
              <div className="mb-4 flex items-center gap-2">
                <span className="text-xl">{categoryIcons[category] ?? "\uD83D\uDCC4"}</span>
                <h3 className="text-lg font-semibold text-text-primary">{category}</h3>
              </div>
              <div className="space-y-2">
                {docTypeValues.map((dtValue) => {
                  const dt = DOC_TYPES.find((d) => d.value === dtValue);
                  if (!dt) return null;
                  return (
                    <div key={dt.value} className="flex items-start gap-3">
                      <code className="shrink-0 rounded bg-surface px-2 py-0.5 text-xs font-semibold text-accent">
                        {dt.value}
                      </code>
                      <span className="text-sm text-text-secondary">{dt.description}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
