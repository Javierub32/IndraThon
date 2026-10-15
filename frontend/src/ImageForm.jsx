import { useState } from "react";

export default function ImageForm() {
  const [image1, setImage1] = useState(null);
  const [image2, setImage2] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setResult(null);

    const formData = new FormData();
    formData.append("image1", image1);
    formData.append("image2", image2);

    try {
      const response = await fetch("/api/process", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "No se pudieron procesar las imágenes.");
      }

      setResult(data);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="block">
          Primera imagen
          <input
            className="mt-1 block"
            type="file"
            accept="image/*,.tif,.tiff"
            required
            onChange={(event) => setImage1(event.target.files[0])}
          />
        </label>

        <label className="block">
          Segunda imagen
          <input
            className="mt-1 block"
            type="file"
            accept="image/*,.tif,.tiff"
            required
            onChange={(event) => setImage2(event.target.files[0])}
          />
        </label>

        <button
          className="rounded bg-blue-600 px-4 py-2 text-white"
          type="submit"
        >
          Procesar con Canny
        </button>
      </form>

      {error && <p className="text-red-600">{error}</p>}

      {result && (
        <section className="grid gap-6 sm:grid-cols-2">
          <figure>
            <figcaption>Resultado de la primera imagen</figcaption>
            <img className="mt-2 max-w-full" src={result.image1} alt="Bordes de la primera imagen" />
          </figure>

          <figure>
            <figcaption>Resultado de la segunda imagen</figcaption>
            <img className="mt-2 max-w-full" src={result.image2} alt="Bordes de la segunda imagen" />
          </figure>
        </section>
      )}
    </main>
  );
}