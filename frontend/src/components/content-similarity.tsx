import { num } from "@/lib/format";

const explanations: Record<string, string> = {
  text_embedding: "Teksty mają podobne znaczenie, nawet gdy użyto innych słów. Samo podobieństwo treści nie dowodzi wspólnego zaplecza.",
  video_frames: "W nagraniach znaleziono podobne klatki, także po ponownym zakodowaniu filmu. Wspólny materiał nie dowodzi wspólnego zaplecza.",
};

export function ContentSimilarity({ kind, similarity }: { kind: string; similarity: number }) {
  if (!explanations[kind]) return null;
  return <p className="px-2 py-1 text-sm text-muted">{explanations[kind]} {kind === "video_frames" ? "Udział zgodnych klatek" : "Podobieństwo kosinusowe"} · {num(similarity, 2)}</p>;
}
