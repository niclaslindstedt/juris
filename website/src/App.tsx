import { Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Hero from "./components/Hero";
import Features from "./components/Features";
import Sources from "./components/Sources";
import DocTypes from "./components/DocTypes";
import GettingStarted from "./components/GettingStarted";
import DocumentationPage from "./components/DocumentationPage";
import ManualPage from "./components/ManualPage";
import Footer from "./components/Footer";
import { usePageMeta } from "./hooks/usePageMeta";

function HomePage() {
  usePageMeta(
    "juris — Swedish Legal Data CLI: Riksdagen, SOU, Domstol, EUR-Lex, ECHR in JSON + Markdown",
    "Open-source Python CLI that collects and normalizes Swedish and EU legal documents (propositioner, SOU, betänkanden, SFS, NJA, EUR-Lex, ECHR…) into a git-friendly database of JSON and Markdown. 21 document types, 8 official sources.",
  );
  return (
    <>
      <Hero />
      <Features />
      <Sources />
      <DocTypes />
      <GettingStarted />
    </>
  );
}

export default function App() {
  return (
    <div className="min-h-screen overflow-x-hidden">
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/docs" element={<DocumentationPage />} />
          <Route path="/docs/:slug" element={<DocumentationPage />} />
          <Route path="/manual" element={<ManualPage />} />
          <Route path="/manual/:command" element={<ManualPage />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
