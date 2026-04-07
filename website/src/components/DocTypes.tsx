import { DOC_TYPES, DOC_TYPE_CATEGORIES } from "../data/sourceData";

const docTypeMap = new Map(DOC_TYPES.map((dt) => [dt.value, dt]));

const CATEGORY_ICONS: Record<string, string> = {
  "Swedish Parliament": "🏛",
  "Swedish Government": "🏢",
  Courts: "⚖",
  Authorities: "🔍",
  "EU Law": "🇪🇺",
};

export default function DocTypes() {
  return (
    <section id="doc-types" className="py-20 px-6">
      <div className="mx-auto max-w-6xl">
        <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">
          Document Types
        </h2>
        <p className="text-text-secondary text-center mb-12 max-w-2xl mx-auto">
          {DOC_TYPES.length} document types across 5 categories of Swedish and European law.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Object.entries(DOC_TYPE_CATEGORIES).map(([category, types]) => (
            <div
              key={category}
              className="p-5 rounded-xl border border-border bg-surface-100"
            >
              <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-4">
                <span className="mr-2">{CATEGORY_ICONS[category]}</span>
                {category}
              </h3>
              <div className="space-y-2">
                {types.map((value) => {
                  const dt = docTypeMap.get(value);
                  if (!dt) return null;
                  return (
                    <div key={value} className="flex items-baseline gap-3">
                      <code className="text-accent font-mono text-sm w-16 shrink-0">
                        {dt.value}
                      </code>
                      <span className="text-text-secondary text-sm">
                        {dt.description}
                      </span>
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
