import { Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Hero from "./components/Hero";
import Features from "./components/Features";
import Sources from "./components/Sources";
import DocTypes from "./components/DocTypes";
import ZagRelationship from "./components/ZagRelationship";
import CodeExamples from "./components/CodeExamples";
import GettingStarted from "./components/GettingStarted";
import Footer from "./components/Footer";
import Documentation from "./components/DocumentationPage";
import Manual from "./components/ManualPage";

function LandingPage() {
  return (
    <>
      <Hero />
      <Features />
      <Sources />
      <DocTypes />
      <ZagRelationship />
      <CodeExamples />
      <GettingStarted />
    </>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-surface overflow-x-hidden">
      <Navbar />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/docs" element={<Documentation />} />
        <Route path="/docs/:slug" element={<Documentation />} />
        <Route path="/manual" element={<Manual />} />
        <Route path="/manual/:slug" element={<Manual />} />
      </Routes>
      <Footer />
    </div>
  );
}
