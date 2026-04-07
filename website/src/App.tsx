import Navbar from "./components/Navbar";
import Hero from "./components/Hero";
import Features from "./components/Features";
import Sources from "./components/Sources";
import DocTypes from "./components/DocTypes";
import GettingStarted from "./components/GettingStarted";
import Footer from "./components/Footer";

export default function App() {
  return (
    <div className="min-h-screen">
      <Navbar />
      <main>
        <Hero />
        <Features />
        <Sources />
        <DocTypes />
        <GettingStarted />
      </main>
      <Footer />
    </div>
  );
}
