import { useEffect, useState } from "react";
import "./index.css";
import ImageForm from "./ImageForm";

function App() {
  const [message, setMessage] = useState("Conectando...");

  useEffect(() => {
    fetch("/api/health")
      .then((response) => response.json())
      .then((data) => setMessage(data.message))
      .catch(() => setMessage("No se pudo conectar con FastAPI"));
  }, []);

  return (
  <div className="min-h-screen flex flex-col items-center justify-center">
    <h2 className="bg-red-500 p-8 text-4xl font-bold text-black">{message}</h2>
	<ImageForm />
  </div>
  );
}

export default App;