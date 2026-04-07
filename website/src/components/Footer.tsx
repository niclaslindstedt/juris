import { VERSION } from "../data/sourceData";

export default function Footer() {
  return (
    <footer className="border-t border-border py-10 px-6">
      <div className="mx-auto max-w-6xl flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-text-dim">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-accent">juris</span>
          <span>v{VERSION}</span>
          <span className="mx-1">·</span>
          <span>MIT License</span>
        </div>
        <div className="flex items-center gap-4">
          <a
            href="https://github.com/niclaslindstedt/juris"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-text-primary transition-colors"
          >
            GitHub
          </a>
          <a
            href="https://pypi.org/project/juris/"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-text-primary transition-colors"
          >
            PyPI
          </a>
        </div>
      </div>
    </footer>
  );
}
