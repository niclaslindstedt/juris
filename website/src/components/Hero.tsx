import Terminal from "./Terminal";

export default function Hero() {
  return (
    <section className="pt-32 pb-20 px-6">
      <div className="mx-auto max-w-6xl">
        {/* Glow effect */}
        <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[300px] md:w-[600px] h-[250px] md:h-[400px] bg-accent/5 rounded-full blur-3xl pointer-events-none" />

        <div className="relative text-center mb-16">
          <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6">
            <span className="bg-gradient-to-r from-accent to-accent-light bg-clip-text text-transparent">
              A git-native database
            </span>
            <br />
            <span className="text-text-primary">for Swedish law</span>
          </h1>
          <p className="text-lg md:text-xl text-text-secondary max-w-2xl mx-auto mb-10">
            Collect and normalize 21 document types from 8 official sources
            into version-controlled JSON + Markdown.
          </p>
          <div className="flex items-center justify-center gap-4 flex-wrap">
            <a
              href="#getting-started"
              className="px-6 py-3 bg-accent hover:bg-accent-light text-surface font-semibold rounded-lg transition-colors"
            >
              Get Started
            </a>
            <a
              href="https://github.com/niclaslindstedt/juris"
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3 border border-border-visible hover:border-accent text-text-primary rounded-lg transition-colors"
            >
              View on GitHub
            </a>
          </div>
        </div>

        <Terminal />
      </div>
    </section>
  );
}
