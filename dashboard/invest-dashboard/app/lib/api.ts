export async function getHistory() {
  const res = await fetch("http://127.0.0.1:3000/api/history", {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error("Failed to fetch history");
  }

  const json = await res.json();
  return json.data || [];
}
