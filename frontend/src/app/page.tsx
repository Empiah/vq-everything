import Image from "next/image";
import { useEffect, useState } from "react";
import ScatterPlot, { Submission } from "../components/ScatterPlot";
import styles from "./page.module.css";

export default function Home() {
  const [submissions, setSubmissions] = useState<Submission[]>([]);

  // Fetch submissions from FastAPI backend
  useEffect(() => {
    fetch("http://localhost:8000/submissions")
      .then((res) => res.json())
      .then((data) => setSubmissions(data))
      .catch((err) => console.error("Failed to fetch submissions:", err));
  }, []);

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <div className="left-panel">
          <h1
            className="prussian-blue-title"
            style={{ fontSize: "2.5rem", marginBottom: "2rem" }}
          >
            Value and Quality Everything
          </h1>
          <div className="plot-container">
            <ScatterPlot data={submissions} />
          </div>
        </div>
        <div className="right-panel">
          <div className="form-container">
            <h2
              className="prussian-blue-title"
              style={{ fontSize: "1.5rem", marginBottom: "1rem" }}
            >
              Add a Submission
            </h2>
            {/* TODO: Submission form will go here */}
            <p style={{ color: "#888", textAlign: "center" }}>
              (Submission form will appear here)
            </p>
          </div>
        </div>
      </main>
      <footer className={styles.footer}>
        <a
          href="https://nextjs.org/learn?utm_source=create-next-app&utm_medium=appdir-template&utm_campaign=create-next-app"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Image
            aria-hidden
            src="/file.svg"
            alt="File icon"
            width={16}
            height={16}
          />
          Learn
        </a>
        <a
          href="https://vercel.com/templates?framework=next.js&utm_source=create-next-app&utm_medium=appdir-template&utm_campaign=create-next-app"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Image
            aria-hidden
            src="/window.svg"
            alt="Window icon"
            width={16}
            height={16}
          />
          Examples
        </a>
        <a
          href="https://nextjs.org?utm_source=create-next-app&utm_medium=appdir-template&utm_campaign=create-next-app"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Image
            aria-hidden
            src="/globe.svg"
            alt="Globe icon"
            width={16}
            height={16}
          />
          Go to nextjs.org →
        </a>
      </footer>
    </div>
  );
}
