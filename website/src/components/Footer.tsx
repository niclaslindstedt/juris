import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="border-t border-border py-12">
      <div className="mx-auto max-w-6xl px-6">
        <div className="flex flex-col items-center justify-between gap-6 md:flex-row">
          <div>
            <span className="text-lg font-bold text-text-primary">
              <span className="text-accent">{"\u2696\uFE0F"}</span> zig
            </span>
            <p className="mt-1 text-sm text-text-dim">
              Swedish legal data, powered by{" "}
              <a href="https://github.com/niclaslindstedt/zag" target="_blank" rel="noopener noreferrer" className="text-zag hover:underline">zag</a>
            </p>
          </div>

          <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-text-secondary">
            <a
              href="https://github.com/niclaslindstedt/juris"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-text-primary transition-colors"
            >
              GitHub
            </a>
            <Link
              to="/docs/overview"
              className="hover:text-text-primary transition-colors"
            >
              Documentation
            </Link>
            <Link
              to="/manual"
              className="hover:text-text-primary transition-colors"
            >
              Manual
            </Link>
            <a
              href="https://pypi.org/project/juris/"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-text-primary transition-colors"
            >
              PyPI
            </a>
            <a
              href="https://github.com/niclaslindstedt/juris/blob/main/LICENSE"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-text-primary transition-colors"
            >
              MIT License
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
