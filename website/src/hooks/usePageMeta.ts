import { useEffect } from "react";

/**
 * Updates the document <title> and <meta name="description"> for the current
 * route. SEO-relevant: lets each SPA route present a distinct title and
 * snippet to crawlers that execute JavaScript (e.g. Googlebot).
 */
export function usePageMeta(title: string, description?: string) {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = title;

    let revertDescription: (() => void) | undefined;
    if (description) {
      const tag = document.querySelector<HTMLMetaElement>(
        'meta[name="description"]',
      );
      if (tag) {
        const previous = tag.content;
        tag.content = description;
        revertDescription = () => {
          tag.content = previous;
        };
      }
    }

    const canonical = document.querySelector<HTMLLinkElement>(
      'link[rel="canonical"]',
    );
    let revertCanonical: (() => void) | undefined;
    if (canonical) {
      const previous = canonical.href;
      canonical.href = window.location.origin + window.location.pathname;
      revertCanonical = () => {
        canonical.href = previous;
      };
    }

    return () => {
      document.title = previousTitle;
      revertDescription?.();
      revertCanonical?.();
    };
  }, [title, description]);
}
