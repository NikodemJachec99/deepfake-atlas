"use client";

import { useParams, useRouter } from "next/navigation";
import { AdCard } from "@/components/ad-card";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  if (!/^[1-9]\d*$/.test(id) || !Number.isSafeInteger(Number(id))) {
    return <p className="p-4">Nieprawidłowy identyfikator reklamy.</p>;
  }
  return <main className="mx-auto w-full max-w-5xl p-4">
    <AdCard adId={Number(id)} full onEdge={edge => router.push(`/investigation?ad=${id}&edge=${edge.id}`)} />
  </main>;
}
