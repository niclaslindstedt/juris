import { Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Hero from "./components/Hero";
import Features from "./components/Features";
import Sources from "./components/Sources";
import DocTypes from "./components/DocTypes";
import GettingStarted from "./components/GettingStarted";
import ManualPage from "./components/ManualPage";
import Footer from "./components/Footer";

function HomePage() {
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
    <div className="min-h-screen">
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/manual" element={<ManualPage />} />
          <Route path="/manual/:command" element={<ManualPage />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
