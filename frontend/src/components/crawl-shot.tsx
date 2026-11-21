import { artifactImageUrl } from "@/lib/api";

export function CrawlShot({ sha }: { sha: unknown }) {
  if (typeof sha !== "string" || !/^[0-9a-f]{64}$/.test(sha)) return null;
  return <figure><figcaption>Zrzut wyrenderowanej strony docelowej</figcaption>
    <a href={artifactImageUrl(sha)} target="_blank" rel="noreferrer">
      {/* eslint-disable-next-line @next/next/no-img-element -- obraz dowodowy z magazynu artefaktów */}
      <img src={artifactImageUrl(sha)} alt="Zrzut strony docelowej" loading="lazy" className="max-h-64 max-w-full object-contain" />
    </a></figure>;
}
