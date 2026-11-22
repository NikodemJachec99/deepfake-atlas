import { ZoomImage } from "./zoom-image";

export function CrawlShot({ sha }: { sha: unknown }) {
  if (typeof sha !== "string" || !/^[0-9a-f]{64}$/.test(sha)) return null;
  return <figure><figcaption>Zrzut wyrenderowanej strony docelowej</figcaption>
    <ZoomImage sha={sha} alt="Zrzut strony docelowej" title="Powiększ zrzut strony" className="max-h-64 max-w-full object-contain" />
  </figure>;
}
