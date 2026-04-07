import { useState, useEffect, useRef, useCallback } from "react";

interface TerminalLine {
  text: string;
  /** Delay in ms before showing this line */
  delay: number;
  /** If true, line is typed char-by-char */
  typed?: boolean;
  /** CSS class for coloring */
  className?: string;
}

const DEMO_LINES: TerminalLine[] = [
  { text: "$ juris collect riksdagen --type prop --session 2024/25", delay: 0, typed: true, className: "text-text-primary" },
  { text: "Collecting prop from riksdagen...", delay: 600, className: "text-text-secondary" },
  { text: "  riksdagen/prop: ████████████████████ 100% (47 saved, 0 skipped)", delay: 1200, className: "text-accent" },
  { text: "", delay: 200 },
  { text: "Done: 47 collected, 0 skipped", delay: 300, className: "text-green-400" },
  { text: "", delay: 800 },
  { text: "$ juris collect-type sou --since 2024-01-01", delay: 0, typed: true, className: "text-text-primary" },
  { text: "Collecting sou from best provider: riksdagen", delay: 600, className: "text-text-secondary" },
  { text: "  riksdagen/sou: ████████████████████ 100% (31 saved, 0 skipped)", delay: 1200, className: "text-accent" },
  { text: "", delay: 200 },
  { text: "Done: 31 collected, 0 skipped", delay: 300, className: "text-green-400" },
  { text: "", delay: 800 },
  { text: "$ juris stats", delay: 0, typed: true, className: "text-text-primary" },
  { text: "  prop     47", delay: 400, className: "text-text-secondary" },
  { text: "  sou      31", delay: 100, className: "text-text-secondary" },
  { text: "  ─────────────", delay: 100, className: "text-text-dim" },
  { text: "  total    78", delay: 100, className: "text-accent" },
];

export default function Terminal() {
  const [visibleLines, setVisibleLines] = useState<{ text: string; className?: string }[]>([]);
  const [currentTyping, setCurrentTyping] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const hasStarted = useRef(false);
  const sectionRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    if (hasStarted.current) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasStarted.current) {
          hasStarted.current = true;
          runDemo();
          observer.disconnect();
        }
      },
      { threshold: 0.3 },
    );

    if (sectionRef.current) observer.observe(sectionRef.current);
    return () => observer.disconnect();
  });

  async function runDemo() {
    for (const line of DEMO_LINES) {
      if (line.delay > 0) {
        await sleep(line.delay);
      }

      if (line.typed) {
        setIsTyping(true);
        for (let i = 0; i <= line.text.length; i++) {
          setCurrentTyping(line.text.slice(0, i));
          scrollToBottom();
          await sleep(25);
        }
        setIsTyping(false);
        setCurrentTyping("");
        setVisibleLines((prev) => [...prev, { text: line.text, className: line.className }]);
      } else {
        setVisibleLines((prev) => [...prev, { text: line.text, className: line.className }]);
      }
      scrollToBottom();
    }
  }

  return (
    <div ref={sectionRef} className="mx-auto max-w-3xl">
      <div className="rounded-xl border border-border-visible overflow-hidden shadow-2xl shadow-black/30">
        {/* Title bar */}
        <div className="flex items-center gap-2 px-4 py-3 bg-surface-200 border-b border-border">
          <div className="w-3 h-3 rounded-full bg-red-500/80" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
          <div className="w-3 h-3 rounded-full bg-green-500/80" />
          <span className="ml-2 text-xs text-text-dim font-mono">terminal</span>
        </div>

        {/* Terminal body */}
        <div
          ref={containerRef}
          className="bg-surface-100 p-4 pb-8 font-mono text-sm leading-6 h-[340px] overflow-y-auto"
        >
          {visibleLines.map((line, i) => (
            <div key={i} className={line.className ?? ""}>
              {line.text || "\u00A0"}
            </div>
          ))}
          {isTyping && (
            <div className="text-text-primary">
              {currentTyping}
              <span className="animate-pulse">█</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
